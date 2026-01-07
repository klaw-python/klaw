---HTTP client for AmpTab API
---@class AmpTabClientModule
local M = {}

local context_mod = require("amptab.context")

---@class AmpTabClient
---@field config AmpTabConfig
---@field current_job any|nil
local Client = {}
Client.__index = Client

---@class AmpTabResult
---@field text string The completion text (rewritten code)
---@field context AmpTabContext Original context
---@field is_preload boolean Whether this was a preload request
---@field time_taken_ms number Time taken for the request

---Create new client
---@param config AmpTabConfig
---@return AmpTabClient
function M.new(config)
  return setmetatable({
    config = config,
    current_job = nil,
  }, Client)
end

---Build request body for AmpTab API
---@param context AmpTabContext
---@param prompt string
---@return table
function Client:build_request_body(context, prompt)
  -- Calculate max tokens based on code to rewrite length
  -- From extension: $8A function calculates this
  local max_tokens = math.max(256, math.floor(#context.code_to_rewrite / 3.5) * 2)

  return {
    stream = true,
    model = self.config.model,
    temperature = self.config.temperature,
    max_tokens = max_tokens,
    response_format = { type = "text" },
    prediction = {
      type = "content",
      content = context.code_to_rewrite,
    },
    stop = { context_mod.TOKENS.EDITABLE_REGION_END },
    prompt = prompt,
  }
end

---Get API key
---@return string
function Client:get_api_key()
  local key = self.config.api_key
  if type(key) == "function" then
    return key()
  end
  return key or ""
end

---Cancel current request
function Client:cancel()
  if self.current_job then
    if type(self.current_job) == "table" and self.current_job.shutdown then
      pcall(function()
        self.current_job:shutdown()
      end)
    end
    self.current_job = nil
  end
end

---Parse SSE data line
---@param line string
---@return string|nil chunk The parsed text chunk, or nil
local function parse_sse_line(line)
  -- SSE format: "data: {...}"
  if not line:match("^data:") then
    return nil
  end

  local json_str = line:gsub("^data:%s*", "")

  -- Handle [DONE] marker
  if json_str == "[DONE]" then
    return nil
  end

  local ok, data = pcall(vim.json.decode, json_str)
  if not ok or not data then
    return nil
  end

  -- OpenAI-compatible format: choices[0].text or choices[0].delta.content
  if data.choices and data.choices[1] then
    local choice = data.choices[1]
    if choice.text then
      return choice.text
    elseif choice.delta and choice.delta.content then
      return choice.delta.content
    end
  end

  return nil
end

---Make completion request
---@param context AmpTabContext
---@param callback fun(result: AmpTabResult|nil, err: string|nil)
function Client:complete(context, callback)
  self:cancel()

  local prompt = context_mod.build_prompt(context)
  local body = self:build_request_body(context, prompt)
  local url = self.config.base_url .. "/api/tab/llm-proxy"
  local api_key = self:get_api_key()

  if api_key == "" then
    callback(nil, "No API key configured")
    return
  end

  local start_time = vim.uv.hrtime()
  local accumulated_text = ""

  -- Use vim.system for HTTP request (Neovim 0.10+)
  local curl_args = {
    "curl",
    "-s",
    "-N", -- disable buffering for streaming
    "-X", "POST",
    "-H", "Content-Type: application/json",
    "-H", "Authorization: Bearer " .. api_key,
    "-d", vim.json.encode(body),
    "--max-time", tostring(math.ceil(self.config.timeout_ms / 1000)),
    url,
  }

  if self.config.debug then
    vim.notify("[AmpTab] Request: " .. url, vim.log.levels.DEBUG)
  end

  self.current_job = vim.system(curl_args, {
    text = true,
    stdout = function(err, data)
      if err then
        vim.schedule(function()
          callback(nil, "Request error: " .. tostring(err))
        end)
        return
      end

      if data then
        -- Parse SSE lines
        for line in data:gmatch("[^\r\n]+") do
          local chunk = parse_sse_line(line)
          if chunk then
            accumulated_text = accumulated_text .. chunk
          end
        end
      end
    end,
  }, function(result)
    self.current_job = nil

    local elapsed_ms = (vim.uv.hrtime() - start_time) / 1e6

    vim.schedule(function()
      if result.code ~= 0 then
        callback(nil, "Request failed with code " .. tostring(result.code))
        return
      end

      -- Clean up the accumulated text
      -- Remove the editable region end marker if present
      local cleaned_text = accumulated_text:gsub(context_mod.TOKENS.EDITABLE_REGION_END, "")

      -- Also handle the start marker if the model included it
      cleaned_text = cleaned_text:gsub(context_mod.TOKENS.EDITABLE_REGION_START, "")

      if cleaned_text == "" or cleaned_text == context.code_to_rewrite then
        callback(nil, nil) -- No completion, but not an error
        return
      end

      callback({
        text = cleaned_text,
        context = context,
        is_preload = false,
        time_taken_ms = elapsed_ms,
      }, nil)
    end)
  end)
end

return M
