---@class AmpTab
---@field config AmpTabConfig
---@field client AmpTabClient
local M = {}

---@class AmpTabConfig
---@field api_key string|fun():string API key or function that returns it
---@field base_url string Base URL for AmpTab API (default: https://ampcode.com)
---@field model string Model to use (default: amp-tab-long-suggestion-model-instruct)
---@field temperature number Temperature for completions (default: 0.1)
---@field timeout_ms number Request timeout in milliseconds (default: 10000)
---@field token_limits AmpTabTokenLimits Token limits for context
---@field debug boolean Enable debug logging

---@class AmpTabTokenLimits
---@field prefix_tokens number
---@field suffix_tokens number
---@field code_to_rewrite_prefix_tokens number
---@field code_to_rewrite_suffix_tokens number

---@type AmpTabConfig
local default_config = {
  api_key = function()
    return vim.env.AMP_API_KEY or ""
  end,
  base_url = "https://ampcode.com",
  model = "amp-tab-long-suggestion-model-instruct",
  temperature = 0.1,
  timeout_ms = 10000,
  token_limits = {
    prefix_tokens = 500,
    suffix_tokens = 500,
    code_to_rewrite_prefix_tokens = 40,
    code_to_rewrite_suffix_tokens = 360,
  },
  debug = false,
}

---@param opts? AmpTabConfig
function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", default_config, opts or {})
  M.client = require("amptab.client").new(M.config)
end

---Get API key (handles both string and function)
---@return string
function M.get_api_key()
  local key = M.config.api_key
  if type(key) == "function" then
    return key()
  end
  return key or ""
end

---Check if AmpTab is available (has valid API key)
---@return boolean
function M.is_available()
  return M.get_api_key() ~= ""
end

---Request completion at current cursor position
---@param callback fun(result: AmpTabResult|nil, err: string|nil)
---@param opts? {bufnr?: number, cursor?: {line: number, col: number}}
function M.complete(callback, opts)
  if not M.is_available() then
    callback(nil, "AmpTab: No API key configured")
    return
  end

  opts = opts or {}
  local bufnr = opts.bufnr or vim.api.nvim_get_current_buf()
  local cursor = opts.cursor or vim.api.nvim_win_get_cursor(0)

  local context = require("amptab.context").build(bufnr, cursor, M.config.token_limits)
  M.client:complete(context, callback)
end

---Cancel any pending requests
function M.cancel()
  if M.client then
    M.client:cancel()
  end
end

return M
