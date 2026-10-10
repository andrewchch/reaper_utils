-- Delete stretch markers in the time selection that are off-grid
-- by more than a user-specified threshold (ms).
--
-- Works on currently selected media items only.
-- Automatically crops stale markers left behind by item splits.
-- Uses the project grid division, independent of the snap toggle.

--------------------------------------------------------------------
-- Logging
--------------------------------------------------------------------

local DEBUG = false  -- set from run dialog below

local function log(msg)
    if DEBUG then
        reaper.ShowConsoleMsg(tostring(msg) .. "\n")
    end
end

--------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------

-- Remove stretch markers that fall outside the item's visible bounds.
-- After a split, REAPER copies ALL markers from the parent take to
-- each resulting item; markers outside the visible range are stale.
local function crop_stretch_markers_to_visible(take)
    local item = reaper.GetMediaItemTake_Item(take)
    if not item then return 0 end

    local item_len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
    local num_markers = reaper.GetTakeNumStretchMarkers(take)
    local removed = 0

    -- Backwards iteration so deletion doesn't shift the indices we need
    for i = num_markers - 1, 0, -1 do
        local ret, pos = reaper.GetTakeStretchMarker(take, i)
        if ret then
            local epsilon = 0.0001  -- ~0.1 ms tolerance
            if pos < -epsilon or pos > (item_len + epsilon) then
                reaper.DeleteTakeStretchMarkers(take, i, nil)
                removed = removed + 1
            end
        end
    end
    return removed
end

-- Snap a project-time position to the nearest grid line, using the
-- project's grid division (projgriddiv). Independent of the snap toggle.
-- projgriddiv is "divisions per quarter note" in REAPER's config.
local function snap_to_project_grid(proj_pos)
    local griddiv = reaper.SNM_GetIntConfigVar("projgriddiv", -1)
    if griddiv <= 0 then
        -- Fallback: use SnapToGrid (respects snap toggle) if config read fails
        return reaper.SnapToGrid(0, proj_pos)
    end

    -- Divisions per quarter note => how many grid lines per QN
    local divisions_per_qn = griddiv

    local qn = reaper.TimeMap2_timeToQN(0, proj_pos)
    local snapped_qn = math.floor(qn * divisions_per_qn + 0.5) / divisions_per_qn
    local grid_pos = reaper.TimeMap2_QNToTime(0, snapped_qn)
    return grid_pos
end

--------------------------------------------------------------------
-- Run dialog
--------------------------------------------------------------------

local default_threshold = 30

local ok, user_input = reaper.GetUserInputs(
    "Delete Off-Grid Stretch Markers",
    2,
    "Threshold (ms):,extrawidth=80" ..
    ",Debug logging (0/1):,extrawidth=80",
    tostring(default_threshold) .. ",0"
)
if not ok then return end

-- local gd = reaper.SNM_GetIntConfigVar("projgriddiv", -1)
-- reaper.ShowConsoleMsg(">>> Grid div: " ..gd)

-- Split the CSV returned by GetUserInputs
local threshold_str, debug_str = user_input:match("^([^,]*),([^,]*)$")
if not threshold_str then
    reaper.ShowConsoleMsg("Unexpected input format.\n")
    return
end

local threshold_ms = tonumber(threshold_str)
local debug_flag   = tonumber(debug_str)

if not threshold_ms or threshold_ms < 0 then
    reaper.ShowConsoleMsg("Invalid threshold.\n")
    return
end
DEBUG = (debug_flag == 1)

local threshold_sec = threshold_ms / 1000.0
log(">>> Threshold = " .. threshold_ms .. " ms (" .. threshold_sec .. " sec)")
log(">>> DEBUG = " .. tostring(DEBUG))

--------------------------------------------------------------------
-- Preconditions
--------------------------------------------------------------------

local ts_start, ts_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
log(">>> Time selection: start=" .. ts_start .. "  end=" .. ts_end ..
    "  length=" .. (ts_end - ts_start))

if ts_start == ts_end then
    log(">>> ABORT: No time selection.")
    return
end

local num_selected = reaper.CountSelectedMediaItems(0)
log(">>> Selected media items: " .. num_selected)

if num_selected == 0 then
    log(">>> ABORT: No items selected.")
    return
end

reaper.Undo_BeginBlock()
reaper.PreventUIRefresh(1)

--------------------------------------------------------------------
-- STEP 1: Crop stale markers to visible item bounds
--------------------------------------------------------------------

log("")
log("=== STEP 1: Cropping stale markers to visible item bounds ===")

local total_cropped = 0
for i = 0, num_selected - 1 do
    local item = reaper.GetSelectedMediaItem(0, i)
    if item then
        local take = reaper.GetActiveTake(item)
        if take then
            local before = reaper.GetTakeNumStretchMarkers(take)
            local removed = crop_stretch_markers_to_visible(take)
            local after  = reaper.GetTakeNumStretchMarkers(take)
            total_cropped = total_cropped + removed

            if removed > 0 then
                log(string.format(
                    "  Item %d: %d -> %d markers (removed %d stale)",
                    i, before, after, removed
                ))
            else
                log(string.format(
                    "  Item %d: %d markers (no stale markers to remove)",
                    i, before
                ))
            end
        end
    end
end

log(">>> Total stale markers removed: " .. total_cropped)
log("")

--------------------------------------------------------------------
-- STEP 2: Find off-grid markers in the time selection
--------------------------------------------------------------------

log("=== STEP 2: Scanning for off-grid markers ===")

local to_delete = {}
local examined = 0
local in_ts = 0

for i = 0, num_selected - 1 do
    local item = reaper.GetSelectedMediaItem(0, i)
    if item then
        local item_start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
        local item_len   = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
        local item_end   = item_start + item_len
        local startoffs  = reaper.GetMediaItemInfo_Value(item, "D_STARTOFFS")

        log("--- Selected item " .. i .. ": start=" .. item_start ..
            "  len=" .. item_len .. "  end=" .. item_end ..
            "  startoffs=" .. startoffs)

        local take = reaper.GetActiveTake(item)
        log("    active take: " .. tostring(take))

        if take then
            local take_rate = reaper.GetMediaItemTakeInfo_Value(take, "D_PLAYRATE")
            log("    take playrate: " .. take_rate)

            local num_markers = reaper.GetTakeNumStretchMarkers(take)
            log("    stretch marker count (post-crop): " .. num_markers)

            local last_valid_pos = nil  -- project position of the last kept marker

            for m = 0, num_markers - 1 do
                local retval, pos, srcpos = reaper.GetTakeStretchMarker(take, m)
                if retval then
                    examined = examined + 1
                    local proj_pos = item_start + pos
                    local in_range = (proj_pos >= ts_start) and (proj_pos <= ts_end)

                    log(string.format(
                        "    SM[%d]: raw_pos=%.9f  srcpos=%.9f  proj_pos=%.9f  in_ts=%s",
                        m, pos, srcpos or -1, proj_pos, tostring(in_range)
                    ))

                    if in_range then
                        in_ts = in_ts + 1
                        local grid_pos = snap_to_project_grid(proj_pos)
                        local dist = math.abs(proj_pos - grid_pos)
                        local over = dist > threshold_sec

                        log(string.format(
                            "        grid_pos=%.9f  dist=%.9f  exceeds_threshold=%s",
                            grid_pos, dist, tostring(over)
                        ))

                        -- Too close to the previous valid marker (< 1 quarter note,
                        -- measured using the tempo at that marker)
                        local too_close = false
                        if last_valid_pos then
                            local last_qn = reaper.TimeMap2_timeToQN(0, last_valid_pos)
                            local qn_interval = reaper.TimeMap2_QNToTime(0, last_qn + 1) - last_valid_pos
                            too_close = (proj_pos - last_valid_pos) < qn_interval
                            log(string.format(
                                "        last_valid_pos=%.9f  qn_interval=%.9f  too_close=%s",
                                last_valid_pos, qn_interval, tostring(too_close)
                            ))
                        end

                        if over or too_close then
                            table.insert(to_delete, {take = take, idx = m})
                            log("        >>> QUEUED FOR DELETION")
                        else
                            last_valid_pos = proj_pos
                        end
                    else
                        last_valid_pos = proj_pos
                    end
                else
                    log("    SM[" .. m .. "]: GetTakeStretchMarker returned false")
                end
            end
        end
    end
end

log("")
log(">>> SUMMARY: examined=" .. examined ..
    "  in_time_selection=" .. in_ts ..
    "  queued=" .. #to_delete)

if #to_delete == 0 then
    log(">>> No off-grid stretch markers found. Nothing to delete.")
    reaper.PreventUIRefresh(-1)
    reaper.UpdateArrange()
    reaper.Undo_EndBlock("Crop stale markers + delete off-grid markers", -1)
    return
end

--------------------------------------------------------------------
-- Confirm and delete
--------------------------------------------------------------------

local msg = string.format(
    "Delete %d stretch marker(s) that are more than %.1f ms from the nearest grid line?",
    #to_delete, threshold_ms
)
local confirm = reaper.ShowMessageBox(msg, "Confirm Deletion", 4)
if confirm ~= 6 then
    log(">>> User declined deletion. Stale-marker crop is preserved.")
    reaper.PreventUIRefresh(-1)
    reaper.UpdateArrange()
    reaper.Undo_EndBlock("Crop stale markers (deletion declined)", -1)
    return
end

local by_take = {}
for _, entry in ipairs(to_delete) do
    local t = entry.take
    if not by_take[t] then by_take[t] = {} end
    table.insert(by_take[t], entry.idx)
end

local deleted_count = 0
for take, indices in pairs(by_take) do
    table.sort(indices, function(a, b) return a > b end)
    for _, idx in ipairs(indices) do
        reaper.DeleteTakeStretchMarkers(take, idx, 1)
        deleted_count = deleted_count + 1
    end
end

reaper.PreventUIRefresh(-1)
reaper.UpdateArrange()
reaper.Undo_EndBlock("Crop stale markers + delete off-grid markers", -1)
log(">>> DONE: deleted " .. deleted_count .. " off-grid marker(s).")
