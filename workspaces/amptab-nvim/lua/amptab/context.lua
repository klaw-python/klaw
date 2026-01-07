---Context builder for AmpTab FIM prompts
---@class AmpTabContextModule
local M = {}

-- Special tokens used by AmpTab
M.TOKENS = {
  EDITABLE_REGION_START = "<|editable_region_start|>",
  EDITABLE_REGION_END = "<|editable_region_end|>",
  USER_CURSOR = "<|user_cursor_is_here|>",
}

-- Approximate chars per token (conservative estimate)
local CHARS_PER_TOKEN = 3.5

---Convert tokens to character count
---@param tokens number
---@return number
local function tokens_to_chars(tokens)
  return math.floor(tokens * CHARS_PER_TOKEN)
end

---Get buffer lines as string
---@param bufnr number
---@param start_line number 0-indexed
---@param end_line number 0-indexed, exclusive
---@return string
local function get_lines(bufnr, start_line, end_line)
  local lines = vim.api.nvim_buf_get_lines(bufnr, start_line, end_line, false)
  return table.concat(lines, "\n")
end

---Get text before cursor up to char limit
---@param bufnr number
---@param cursor {[1]: number, [2]: number} 1-indexed line, 0-indexed col
---@param max_chars number
---@return string
local function get_prefix(bufnr, cursor, max_chars)
  local line = cursor[1] - 1 -- 0-indexed
  local col = cursor[2]

  -- Get current line up to cursor
  local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
  local current_prefix = current_line:sub(1, col)

  -- Get preceding lines
  local prefix_lines = {}
  local char_count = #current_prefix
  local start_line = line - 1

  while start_line >= 0 and char_count < max_chars do
    local prev_line = vim.api.nvim_buf_get_lines(bufnr, start_line, start_line + 1, false)[1] or ""
    char_count = char_count + #prev_line + 1 -- +1 for newline
    table.insert(prefix_lines, 1, prev_line)
    start_line = start_line - 1
  end

  table.insert(prefix_lines, current_prefix)
  local result = table.concat(prefix_lines, "\n")

  -- Trim to max_chars from the end (keep most recent)
  if #result > max_chars then
    result = result:sub(-max_chars)
  end

  return result
end

---Get text after cursor up to char limit
---@param bufnr number
---@param cursor {[1]: number, [2]: number} 1-indexed line, 0-indexed col
---@param max_chars number
---@return string
local function get_suffix(bufnr, cursor, max_chars)
  local line = cursor[1] - 1 -- 0-indexed
  local col = cursor[2]
  local line_count = vim.api.nvim_buf_line_count(bufnr)

  -- Get current line after cursor
  local current_line = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)[1] or ""
  local current_suffix = current_line:sub(col + 1)

  -- Get following lines
  local suffix_lines = { current_suffix }
  local char_count = #current_suffix
  local end_line = line + 1

  while end_line < line_count and char_count < max_chars do
    local next_line = vim.api.nvim_buf_get_lines(bufnr, end_line, end_line + 1, false)[1] or ""
    char_count = char_count + #next_line + 1 -- +1 for newline
    table.insert(suffix_lines, next_line)
    end_line = end_line + 1
  end

  local result = table.concat(suffix_lines, "\n")

  -- Trim to max_chars from the start (keep closest to cursor)
  if #result > max_chars then
    result = result:sub(1, max_chars)
  end

  return result
end

---@class AmpTabContext
---@field prefix_before_editable string Text before the editable region
---@field code_to_rewrite_prefix string Editable region text before cursor
---@field code_to_rewrite_suffix string Editable region text after cursor
---@field suffix_after_editable string Text after the editable region
---@field code_to_rewrite string Full editable region (prefix + suffix)
---@field cursor {line: number, col: number} 0-indexed cursor position
---@field range {start_line: number, end_line: number, start_col: number, end_col: number} 0-indexed range
---@field bufnr number Buffer number
---@field filetype string

---Build context for AmpTab completion
---@param bufnr number
---@param cursor {[1]: number, [2]: number} 1-indexed line, 0-indexed col from nvim_win_get_cursor
---@param token_limits AmpTabTokenLimits
---@return AmpTabContext
function M.build(bufnr, cursor, token_limits)
  local prefix_chars = tokens_to_chars(token_limits.prefix_tokens)
  local suffix_chars = tokens_to_chars(token_limits.suffix_tokens)
  local rewrite_prefix_chars = tokens_to_chars(token_limits.code_to_rewrite_prefix_tokens)
  local rewrite_suffix_chars = tokens_to_chars(token_limits.code_to_rewrite_suffix_tokens)

  -- Code to rewrite = smaller region around cursor that can be replaced
  local code_to_rewrite_prefix = get_prefix(bufnr, cursor, rewrite_prefix_chars)
  local code_to_rewrite_suffix = get_suffix(bufnr, cursor, rewrite_suffix_chars)

  -- Calculate the range that code_to_rewrite spans
  local cursor_line = cursor[1] - 1 -- 0-indexed
  local cursor_col = cursor[2]

  -- Count newlines in prefix to find start line
  local prefix_newlines = select(2, code_to_rewrite_prefix:gsub("\n", ""))
  local start_line = cursor_line - prefix_newlines

  -- Find start column (chars after last newline in prefix)
  local last_newline = code_to_rewrite_prefix:match(".*\n()")
  local start_col = last_newline and (#code_to_rewrite_prefix - last_newline + 1) or 0

  -- Count newlines in suffix to find end line
  local suffix_newlines = select(2, code_to_rewrite_suffix:gsub("\n", ""))
  local end_line = cursor_line + suffix_newlines

  -- Find end column
  local suffix_last_newline = code_to_rewrite_suffix:match(".*\n()")
  local end_col
  if suffix_last_newline then
    end_col = #code_to_rewrite_suffix - suffix_last_newline + 1
  else
    end_col = cursor_col + #code_to_rewrite_suffix
  end

  -- Prefix/suffix = larger context window around the editable region
  -- We need text BEFORE the editable region and AFTER it
  local full_prefix = get_prefix(bufnr, cursor, prefix_chars + rewrite_prefix_chars)
  local full_suffix = get_suffix(bufnr, cursor, suffix_chars + rewrite_suffix_chars)

  -- Extract the parts outside the editable region
  local prefix_before_editable = full_prefix:sub(1, math.max(0, #full_prefix - #code_to_rewrite_prefix))
  local suffix_after_editable = full_suffix:sub(#code_to_rewrite_suffix + 1)

  return {
    prefix_before_editable = prefix_before_editable,
    code_to_rewrite_prefix = code_to_rewrite_prefix,
    code_to_rewrite_suffix = code_to_rewrite_suffix,
    suffix_after_editable = suffix_after_editable,
    code_to_rewrite = code_to_rewrite_prefix .. code_to_rewrite_suffix,
    cursor = { line = cursor_line, col = cursor_col },
    range = {
      start_line = start_line,
      end_line = end_line,
      start_col = start_col,
      end_col = end_col,
    },
    bufnr = bufnr,
    filetype = vim.bo[bufnr].filetype,
  }
end

---Build the FIM prompt message for AmpTab
---@param context AmpTabContext
---@return string
function M.build_prompt(context)
  -- Format:
  -- <prefix_before_editable>
  -- <|editable_region_start|>
  -- <code_to_rewrite_prefix><|user_cursor_is_here|><code_to_rewrite_suffix>
  -- <|editable_region_end|>
  -- <suffix_after_editable>
  --
  -- The model should return the rewritten editable region

  local parts = {
    context.prefix_before_editable,
    M.TOKENS.EDITABLE_REGION_START,
    context.code_to_rewrite_prefix,
    M.TOKENS.USER_CURSOR,
    context.code_to_rewrite_suffix,
    M.TOKENS.EDITABLE_REGION_END,
    context.suffix_after_editable,
  }

  return table.concat(parts, "")
end

return M
