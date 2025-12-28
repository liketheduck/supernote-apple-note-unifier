# Supernote Text Box Format - Reverse Engineering Documentation

**Date:** 2024-12-27
**Source:** Sample .note file with text boxes (created on Supernote Manta)
**Contains:** 3 text boxes - Normal, Bold, and Italic text

## Overview

Text boxes in Supernote .note files are stored in the **TOTALPATH** block of each page. This is different from handwritten strokes which are stored in layer bitmaps.

## File Structure

### Page Metadata

When a page contains text boxes, the page metadata includes:

```
<PAGETEXTBOX:1>
<DISABLE:720,240,254,112|748,616,351,112|960,1272,377,112|>
<TOTALPATH:20870>
```

- `PAGETEXTBOX`: Flag indicating text boxes are present (1 = yes)
- `DISABLE`: Pipe-separated list of text box bounding rectangles (`x,y,width,height`)
- `TOTALPATH`: Address of the TOTALPATH block containing text box data

### TOTALPATH Block Structure

The TOTALPATH block contains:

1. **Binary Header** (variable length, ~491 bytes for 3 text boxes)
2. **Text Box Data** (Base64-encoded CSV for each text box)

#### Binary Header (491 bytes)

| Offset | Size | Type | Description | Example Value |
|--------|------|------|-------------|---------------|
| 0-3 | 4 | uint32 | Text box count | 3 |
| 4-7 | 4 | uint32 | Unknown (possibly data length) | 814 |
| 8-15 | 8 | bytes | Zeros | 00 00 00 00 00 00 00 00 |
| 16-19 | 4 | uint32 | Unknown | 100 |
| 20-55 | 36 | bytes | Header data + "0000" marker | |
| 56-107 | 52 | bytes | Padding zeros | |
| 108-111 | 4 | uint32 | First textbox X position | 720 |
| 112-115 | 4 | uint32 | First textbox Y position | 240 |
| 116-191 | 76 | bytes | Additional position/extent data | |
| 192-219 | 28 | bytes | Flags | |
| 220-223 | 4 | uint32 | Path point count | 5 (closed rectangle) |
| 224-263 | 40 | bytes | Path coordinates (int32 pairs) | Closed rectangle path |
| 264-491 | ~227 | bytes | Additional flags and data | |

## Text Box Data Format

Each text box is stored as a comma-separated string of **20 Base64-encoded fields**:

### Field Structure

| Field | Description | Example (Normal) | Example (Bold) | Example (Italic) |
|-------|-------------|------------------|----------------|------------------|
| 0 | Unknown | `MA==` (0) | `MA==` (0) | `MA==` (0) |
| 1 | Unknown | `MA==` (0) | `MA==` (0) | `MA==` (0) |
| 2 | Unknown | `MA==` (0) | `MA==` (0) | `MA==` (0) |
| 3 | Timestamp/ID | `MjAyNTEyMjcyMDI1NTgz...` | ... | ... |
| 4 | Initial rect | `NzIwLDI0MCwyNTQsMTEy` (720,240,254,112) | 748,616,351,112 | 960,1272,377,112 |
| 5 | Current rect | Same as field 4 | Same as field 4 | Same as field 4 |
| 6 | Unknown | `bm9uZQ==` (none) | none | none |
| 7 | Unknown | `bm9uZQ==` (none) | none | none |
| 8 | Unknown | `bm9uZQ==` (none) | none | none |
| 9 | Unknown | `MA==` (0) | 0 | 0 |
| 10 | Font size | `ODYuMDAwMDAw` (86.000000) | 86.000000 | 86.000000 |
| 11 | Font path | `/storage/emulated/0/.data/fonts/Dolce.otf` | Same | Same |
| **12** | **TEXT CONTENT** | `Tm9ybWFs` (**Normal**) | **This is bold** | **This is italic** |
| **13** | **Style flags** | See below | See below | See below |
| 14 | Height | `MTEy` (112) | 112 | 112 |
| 15 | Unknown | `MQ==` (1) | 1 | 1 |
| 16 | Unknown | `MQ==` (1) | 1 | 1 |
| 17 | Unknown | `MA==` (0) | 0 | 0 |
| 18 | Unknown | `bm9uZQ==` (none) | none | none |
| 19 | Terminator | Empty | Empty | Empty |

### Style Flags (Field 13)

The style flags field is a comma-separated string with 18+ values:

```
0,0,0,0.000000,0.000000,1.000000,1,1,BOLD,0,0,ITALIC,1,3,0,255,255,0,
```

| Index | Description | Normal | Bold | Italic |
|-------|-------------|--------|------|--------|
| 0-2 | Unknown | 0,0,0 | 0,0,0 | 0,0,0 |
| 3-4 | Rotation/Transform | 0.0,0.0 | 0.0,0.0 | 0.0,0.0 |
| 5 | Scale | 1.0 | 1.0 | 1.0 |
| 6-7 | Unknown | 1,1 | 1,1 | 1,1 |
| **8** | **BOLD FLAG** | **0** | **1** | **0** |
| 9-10 | Unknown | 0,0 | 0,0 | 0,0 |
| **11** | **ITALIC FLAG** | **0** | **0** | **1** |
| 12-14 | Unknown | 1,3,0 | 1,3,0 | 1,3,0 |
| 15-16 | Color (R,G?) | 255,255 | 255,255 | 255,255 |
| 17 | Unknown | 0 | 0 | 0 |

## Key Findings

### Text Styling

- **Bold**: Set style index 8 to `1`
- **Italic**: Set style index 11 to `1`
- **Bold + Italic**: Set both index 8 AND 11 to `1`

### Fonts

- Default font: `Dolce.otf`
- Font path: `/storage/emulated/0/.data/fonts/Dolce.otf`
- Default font size: 86.0 pixels

### Coordinates

- Page dimensions: 1920 x 2560 (Manta/A5X2)
- Text box coordinates: x, y, width, height in pixels
- Origin: Top-left corner

### Bounding Boxes

The `DISABLE` field in page metadata contains the bounding rectangles for hit testing:
```
720,240,254,112|748,616,351,112|960,1272,377,112
```

Each rectangle format: `x,y,width,height`

## Creating Text Boxes

To create a .note file with text boxes:

1. Set `PAGETEXTBOX: 1` in page metadata
2. Add `DISABLE: <x,y,w,h>|...` for each text box
3. Create TOTALPATH block with:
   - Binary header (use template from existing file)
   - Text box count at offset 0
   - First text box position at offsets 108-115
   - Base64-encoded text box data following header
4. Set `TOTALPATH: <address>` in page metadata

### Text Box Template

```python
import base64

def create_textbox_data(text, x, y, width, height, bold=False, italic=False):
    timestamp = "20251227202558315106"  # Generate unique timestamp
    rect = f"{x},{y},{width},{height}"
    font_path = "/storage/emulated/0/.data/fonts/Dolce.otf"
    font_size = "86.000000"

    bold_flag = "1" if bold else "0"
    italic_flag = "1" if italic else "0"
    style = f"0,0,0,0.000000,0.000000,1.000000,1,1,{bold_flag},0,0,{italic_flag},1,3,0,255,255,0,"

    fields = [
        "0", "0", "0",
        timestamp,
        rect, rect,
        "none", "none", "none",
        "0",
        font_size,
        font_path,
        text,
        style,
        str(height),
        "1", "1", "0",
        "none", ""
    ]

    return ",".join(base64.b64encode(f.encode()).decode() for f in fields)
```

## Files

- Sample file: A .note file with text boxes (available on your Supernote device under `Note/`)
- File size: 24,813 bytes (reference)
- Text boxes: 3 (Normal, Bold, Italic)

## Investigation Log

### Attempt 1: Basic Text Box Generation (CRASHED)

Created `test_textbox.note` with:
- TOTALPATH block with text box data
- Empty layer bitmaps (LAYERBITMAP: 0)
- BGLAYER with protocol "BGLAYER"
- Missing several page metadata fields

**Result:** File crashed Supernote device on open.

### Attempt 2: Fixed Layer Protocols and Metadata (TESTING)

Compared native file structure with generated file:

#### Native vs Generated Differences

| Aspect | Native | Generated v1 | Fix Applied |
|--------|--------|--------------|-------------|
| File size | 24,813 bytes | ~4,000 bytes | Need real layer data |
| MAINLAYER bitmap | 20,609 bytes | 0 bytes | Added blank RLE |
| BGLAYER bitmap | 429 bytes | 0 bytes | Added blank RLE |
| BGLAYER protocol | RATTA_RLE | BGLAYER | Fixed to RATTA_RLE |
| Page RECOGNTYPE | Present | Missing | Added |
| Page RECOGNFILESTATUS | Present | Missing | Added |
| Page RECOGNLANGUAGE | Present | Missing | Added |
| Page EXTERNALLINKINFO | Present | Missing | Added |
| Page IDTABLE | Present | Missing | Added |

#### Key Findings

1. **Layer Bitmaps Are Required**
   - Even for text-only pages, MAINLAYER and BGLAYER must contain valid RLE data
   - Native file: MAINLAYER has ~20KB of bitmap data (includes text box visuals)
   - Native file: BGLAYER has 429 bytes (background style lines)

2. **BGLAYER Uses RATTA_RLE Protocol**
   - NOT "BGLAYER" protocol as might be assumed
   - Same compression as MAINLAYER

3. **Missing Page Metadata Fields**
   Required fields that were missing:
   ```
   <RECOGNTYPE:0>
   <RECOGNFILESTATUS:0>
   <RECOGNLANGUAGE:none>
   <EXTERNALLINKINFO:0>
   <IDTABLE:0>
   ```

4. **Bitmap Content**
   - Native MAINLAYER contains rendered text with visible pixels
   - Pattern shows vertical lines at regular intervals (text box borders?)
   - Uses RLE with values like: `62 b3 62 71 61 8c 61 1b`

### Layer Bitmap Analysis

Native MAINLAYER RLE pattern (hex excerpt at offset 0x1c8):
```
62 b3 62 71 61 8c 61 1b 62 ff 62 ff 62 ff 62 ff
```

Interpretation:
- `62 xx` = run of `xx` white pixels (62 = RLE escape, ff = 255 count)
- `61 xx` = different encoding (background?)
- The non-ff values indicate actual drawn content

### Open Questions

1. **Does Supernote render text boxes from TOTALPATH data?**
   - Or are pre-rendered bitmaps required?
   - Native file has bitmap content, but is it required?

2. **What is the minimum viable bitmap?**
   - Can we use blank (all white) bitmaps?
   - Or must we pre-render the text boxes?

3. **LAYERINFO Format**
   - Native uses `#` instead of `:` in JSON-like format
   - Example: `{"layerId"#3,"name"#"Layer 3",...}`
   - Generated uses standard JSON with `:`

### Attempt 3: Modified Native File (Same-Length Text)

Created v4 by replacing "Normal" with "Python" in the native file:
- Both strings are 6 characters = same Base64 length (8 chars)
- File size unchanged: 24,813 bytes
- Parses correctly with supernotelib
- **Result: TESTING on Supernote device**

Key insight: Block offsets in metadata must be exact. Changing content length without updating offsets causes crashes.

### TOTALPATH Binary Header Analysis (491 bytes)

Detailed offset map:
| Offset | Size | Description | Value (3 boxes) |
|--------|------|-------------|-----------------|
| 0-3 | 4 | Text box count | 3 |
| 4-7 | 4 | Data size (after header) | 814 |
| 8-15 | 8 | Zeros | 0 |
| 16-19 | 4 | Unknown | 100 (0x64) |
| 20-23 | 4 | Unknown | 0 |
| 24-27 | 4 | Unknown | 32 |
| 28-31 | 4 | Unknown | 32 |
| 32-39 | 8 | Zeros | 0 |
| 40-43 | 4 | Unknown | 1 |
| 44-55 | 12 | Zeros | 0 |
| 56-59 | 4 | ASCII "0000" | "0000" |
| 60-107 | 48 | Zeros | 0 |
| 108-111 | 4 | First box X (float) | 720.0 |
| 112-115 | 4 | First box Y (float) | 240.0 |
| ... | ... | More position data | ... |

### Files Created

- `/tmp/test_textbox.note` - First attempt (crashed)
- `/tmp/test_textbox_v2.note` - Second attempt with metadata fixes (testing)
- `/tmp/test_textbox_v3.note` - Modified native with longer text (wrong size)
- `/tmp/test_textbox_v4.note` - Modified native with same-length text (testing)
- `/research/totalpath_header_template.bin` - 491-byte binary header template
- `/research/blank_rle_template.bin` - Minimal blank page RLE

### Attempt 4: From-Scratch Build (v5)

Created complete file from scratch with:
- Proper blank RLE bitmaps (600 bytes each)
- Correct metadata structure with all required fields
- Supernote's `#` delimiter format in LAYERINFO
- Proper TOTALPATH header from template
- All block addresses calculated correctly

**Result: TESTING on Supernote device**

### RLE Encoding Details

The RATTA_RLE format uses:
- `0x62` = background/white color
- `0x61` = black color
- `0xff` = special marker = 16,384 pixels (0x4000)
- Values 0x00-0xFE = length + 1 pixels

For a blank 1920x2560 page:
- Total pixels: 4,915,200
- Pixels per 0xff marker: 16,384
- Number of runs: 300 (exactly)
- Blank RLE size: 600 bytes

This is much smaller than native files (18KB+) because native files contain rendered text box visuals.

### Test Files Summary

| File | Size | Description | Status |
|------|------|-------------|--------|
| Test Text Box.note | 3,259 | Original v1 | CRASHED |
| Test Text Box v2.note | 4,089 | Metadata fixes | TESTING |
| Test Text Box v3.note | 24,829 | Modified native (wrong size) | TESTING |
| Test Text Box v4.note | 24,813 | Modified native (same size) | TESTING |
| Test Text Box v5.note | 4,089 | Complete from-scratch | TESTING |
| Test Reconstructed.note | 24,171 | supernotelib reconstruct | TESTING |

## Next Steps

1. ~~Extract complete binary header template~~ Done
2. ~~Implement text box generator in Python~~ Done
3. ~~Create blank RLE bitmap encoder~~ Done (600 bytes)
4. ~~Build complete from-scratch file~~ Done (v5)
5. Test all files on Supernote device
6. If blank bitmaps fail, implement text rendering to bitmap
7. Handle multi-line text boxes
8. Handle mixed formatting within single text box
