# Supernote .note File Format Analysis

This document provides a comprehensive analysis of the Supernote `.note` file format, based on reverse engineering using `supernotelib` and hex dump analysis.

## Table of Contents
1. [File Overview](#file-overview)
2. [File Header Structure](#file-header-structure)
3. [File Footer Structure](#file-footer-structure)
4. [Page Structure](#page-structure)
5. [Layer System](#layer-system)
6. [Recognition Data](#recognition-data)
7. [Custom Backgrounds/Templates](#custom-backgroundstemplates)
8. [PDF Annotation Files (.mark)](#pdf-annotation-files-mark)
9. [Creating .note Files](#creating-note-files)

---

## File Overview

### Magic Bytes and Signature
```
Offset 0x00: "note" (4 bytes) - File type identifier
Offset 0x04: "SN_FILE_VER_XXXXXXXX" - Version signature
```

Example signature: `SN_FILE_VER_20230015` (Chauvet 3.14.27 firmware)

### Known Signatures (X-series)
| Signature | Firmware Version |
|-----------|------------------|
| SN_FILE_VER_20200001 | C.053 |
| SN_FILE_VER_20200005 | C.077 |
| SN_FILE_VER_20200006 | C.130 |
| SN_FILE_VER_20200007 | C.159 |
| SN_FILE_VER_20200008 | C.237 |
| SN_FILE_VER_20210009 | C.291 |
| SN_FILE_VER_20210010 | Chauvet 2.1.6 |
| SN_FILE_VER_20220011 | Chauvet 2.5.17 |
| SN_FILE_VER_20220013 | Chauvet 2.6.19 |
| SN_FILE_VER_20230014 | Chauvet 2.10.25 |
| SN_FILE_VER_20230015 | Chauvet 3.14.27 |

### Page Dimensions
| Device | Width | Height |
|--------|-------|--------|
| A5X/A6X | 1404 | 1872 |
| A5X2/N5 | 1920 | 2560 |

### Binary Structure Overview
```
[Type: 4 bytes]["note"]
[Signature: ~20 bytes]["SN_FILE_VER_XXXXXXXX"]
[Header Block]
[Cover Block (optional)]
[Keyword Blocks (optional)]
[Title Blocks (optional)]
[Link Blocks (optional)]
[Style/Background Blocks]
[Page Blocks...]
[Footer Block]
["tail": 4 bytes]
[Footer Address: 4 bytes]
```

---

## File Header Structure

The header is stored as a metadata block with key-value pairs in XML-like format:
`<KEY:VALUE><KEY2:VALUE2>...`

### Header Fields

| Field | Description | Example |
|-------|-------------|---------|
| MODULE_LABEL | Module identifier | `none` |
| FILE_TYPE | File type | `NOTE` or `MARK` |
| APPLY_EQUIPMENT | Device type | `N5` (A5X2) |
| FINALOPERATION_PAGE | Last edited page | `3` |
| FINALOPERATION_LAYER | Last edited layer | `1` |
| DEVICE_DPI | Device DPI | `0` |
| SOFT_DPI | Software DPI | `0` |
| FILE_PARSE_TYPE | Parse type | `0` |
| RATTA_ETMD | Unknown | `0` |
| APP_VERSION | App version | `0` |
| FILE_ID | Unique file identifier | `F202509181349339551651eDSGpQglNVu` |
| FILE_RECOGN_TYPE | Recognition type | `1` (realtime), `0` (none) |
| FILE_RECOGN_LANGUAGE | OCR language | `en_US` |
| PDFSTYLE | PDF style reference | `none` |
| PDFSTYLEMD5 | PDF style hash | `0` |
| STYLEUSAGETYPE | Style usage | `0` |
| HIGHLIGHTINFO | Highlight data | `0` |
| HORIZONTAL_CHECK | Orientation flag | `0` |
| IS_OLD_APPLY_EQUIPMENT | Legacy equipment | `1` |
| ANTIALIASING_CONVERT | Antialiasing setting | `2` |

### File ID Format
```
F[YYYYMMDDHHMMSS][milliseconds][random_string]
Example: F202509181349339551651eDSGpQglNVu
```

---

## File Footer Structure

The footer is located at the end of the file. The last 4 bytes point to the footer block address.

### Footer Fields

| Field | Description |
|-------|-------------|
| FILE_FEATURE | Address of header block |
| PAGE1, PAGE2, ... | Page block addresses |
| COVER_0 or COVER_2 | Cover image address |
| STYLE_[name][hash] | Custom style addresses |
| KEYWORD_[id] | Keyword block addresses |
| TITLE_[id] | Title block addresses |
| LINK[id] | Link block addresses |

---

## Page Structure

Each page has its own metadata block containing:

### Page Metadata Fields

| Field | Description | Example |
|-------|-------------|---------|
| PAGESTYLE | Template/style name | `user_6mm lines plain` |
| PAGESTYLEMD5 | Style hash (MD5) | `8558826856616b5388d4effb77a6d349` |
| LAYERINFO | JSON layer configuration | See below |
| LAYERSEQ | Active layer sequence | `MAINLAYER,BGLAYER` |
| MAINLAYER | Main layer address | `46920` |
| LAYER1 | Layer 1 address | `0` |
| LAYER2 | Layer 2 address | `0` |
| LAYER3 | Layer 3 address | `0` |
| BGLAYER | Background layer address | `47053` |
| TOTALPATH | Stroke path data address | `47182` |
| THUMBNAILTYPE | Thumbnail type | `0` |
| RECOGNSTATUS | Recognition status | `0`=none, `1`=done, `2`=running |
| RECOGNTEXT | Recognition text address | `732448` |
| RECOGNFILE | Recognition file address | `733184` |
| PAGEID | Unique page identifier | `P20250918134933965710SBzB0QvB1SHm` |
| ORIENTATION | Page orientation | `1000`=vertical, `1090`=horizontal |
| PAGETEXTBOX | Text box data | `0` |

### LAYERINFO JSON Structure
```json
[
  {"layerId": 3, "name": "Layer 3", "isBackgroundLayer": false,
   "isCurrentLayer": false, "isVisible": true, "isDeleted": true},
  {"layerId": 2, "name": "Layer 2", ...},
  {"layerId": 1, "name": "Layer 1", ...},
  {"layerId": 0, "name": "Main Layer", "isCurrentLayer": true, "isDeleted": false},
  {"layerId": -1, "name": "Background Layer", "isBackgroundLayer": true}
]
```

### Page ID Format
```
P[YYYYMMDDHHMMSS][milliseconds][random_string]
Example: P20250918134933965710SBzB0QvB1SHm
```

---

## Layer System

### Layer Types

| Layer Name | Index | Purpose |
|------------|-------|---------|
| MAINLAYER | 0 | Primary drawing layer (user strokes) |
| LAYER1 | 1 | Additional layer 1 |
| LAYER2 | 2 | Additional layer 2 |
| LAYER3 | 3 | Additional layer 3 |
| BGLAYER | 4 | Background/template layer |

### Layer Metadata

Each layer block contains:

| Field | Description | Example |
|-------|-------------|---------|
| LAYERTYPE | Layer type | `NOTE` |
| LAYERPROTOCOL | Encoding protocol | `RATTA_RLE` |
| LAYERNAME | Layer name | `MAINLAYER` |
| LAYERPATH | Path data address | `0` |
| LAYERBITMAP | Bitmap data address | `21050` |
| LAYERVECTORGRAPH | Vector data address | `0` |
| LAYERRECOGN | Recognition data address | `0` |

### Encoding Protocols

1. **RATTA_RLE** - Run-length encoding used for X-series
   - Color codes:
     - `0x61` - Black
     - `0x62` - Background (transparent)
     - `0x63` - Dark Gray
     - `0x64` - Gray
     - `0x65` - White
     - `0x66` - Marker Black
     - `0x67` - Marker Dark Gray
     - `0x68` - Marker Gray

2. **X2 Series Color Codes** (different from X-series):
   - `0x9D` - Dark Gray
   - `0xC9` - Gray
   - `0x9E` - Marker Dark Gray
   - `0xCA` - Marker Gray

3. **SN_ASA_COMPRESS** - Zlib compression (original Supernote)

### BGLAYER Content
The background layer (BGLAYER) contains a PNG image for custom templates:
- Resolution: 1920x2560 (A5X2) or 1404x1872 (A5X/A6X)
- Format: 8-bit RGB PNG
- The PNG is stored directly in the layer content

---

## Recognition Data

### Recognition Text (RECOGNTEXT)
- Base64-encoded JSON containing OCR results
- Structure:
```json
{
  "elements": [
    {"type": "Raw Content"},
    {
      "type": "Text",
      "label": "recognized text",
      "words": [
        {
          "bounding-box": {"x": 19.96, "y": 14.16, "width": 39.2, "height": 10.46},
          "label": "word"
        }
      ]
    }
  ]
}
```

### Recognition File (RECOGNFILE)
- ZIP archive containing ink data
- Path structure: `pages/[pageid]/ink.bink`
- Used for handwriting recognition

---

## Custom Backgrounds/Templates

### How Custom Templates Work

1. **Template Storage Location**
   - Templates stored in: `/Supernote/MyStyle/[folder]/`
   - File format: PNG images (1920x2560 for A5X2)

2. **Template Naming Convention**
   - PAGESTYLE: `user_[template_name]`
   - Example: `user_6mm lines plain`

3. **MD5 Hash**
   - PAGESTYLEMD5 is the MD5 hash of the template name
   - Used to uniquely identify the template

4. **Footer Reference**
   - Footer contains: `STYLE_user_[name][md5hash]: [address]`
   - Example: `STYLE_user_6mm lines plain8558826856616b5388d4effb77a6d349: 430`

5. **Sharing Across Pages**
   - Same template content is stored once in the file
   - All pages using the same template reference the same address
   - BGLAYER metadata points to the shared template data

### Creating Custom Backgrounds

To embed a PDF page or custom image as background:

1. Render PDF page to PNG (1920x2560 for A5X2)
2. Store PNG data in a background block
3. Set PAGESTYLE to `user_[descriptive_name]`
4. Calculate MD5 hash of the style name
5. Reference the background in BGLAYER

---

## PDF Annotation Files (.mark)

PDF annotations are stored in separate `.mark` files alongside the PDF.

### .mark File Structure

Same format as `.note` files but:
- FILE_TYPE: `MARK`
- Type identifier: `mark` (not `note`)
- BGLAYER: Usually `0` (PDF provides background)
- PAGESTYLE: `none`

### PDF-Note Relationship
- PDF: `/Supernote/Document/path/file.pdf`
- Annotations: `/Supernote/Document/path/file.pdf.mark`

The .mark file contains only the annotation strokes, not the PDF content itself. The Supernote device renders the PDF and overlays the annotations.

---

## Creating .note Files

### Using supernotelib's NotebookBuilder

The `manipulator.py` module provides `NotebookBuilder` for creating .note files:

```python
from supernotelib import NotebookBuilder

builder = NotebookBuilder()

# 1. Pack type and signature
builder.append('__type__', b'note', skip_block_size=True)
builder.append('__signature__', b'SN_FILE_VER_20230015', skip_block_size=True)

# 2. Pack header
header_block = _construct_metadata_block(header_dict)
builder.append('__header__', header_block)

# 3. Pack backgrounds/styles
builder.append('STYLE_user_mytemplate[md5]', png_data)

# 4. Pack page layers
builder.append('PAGE1/MAINLAYER/LAYERBITMAP', mainlayer_data)
builder.append('PAGE1/MAINLAYER/metadata', layer_metadata_block)
builder.append('PAGE1/BGLAYER/metadata', bglayer_metadata_block)
builder.append('PAGE1/metadata', page_metadata_block)

# 5. Pack footer
builder.append('__footer__', footer_block)
builder.append('__tail__', b'tail', skip_block_size=True)
builder.append('__footer_address__', footer_addr.to_bytes(4, 'little'), skip_block_size=True)

# Build final binary
binary_data = builder.build()
```

### Metadata Block Format

```python
def _construct_metadata_block(info_dict):
    block_data = ''
    for k, v in info_dict.items():
        if type(v) == list:
            for e in v:
                block_data += f'<{k}:{e}>'
        else:
            block_data += f'<{k}:{v}>'
    return block_data.encode('utf-8')
```

### Key Steps for PDF-to-Note Conversion

1. **Render PDF pages to PNG** (1920x2560 for A5X2)
2. **Create minimal .note file structure**
3. **For each page:**
   - Store PNG as BGLAYER content
   - Create empty MAINLAYER (for user annotations)
   - Set PAGESTYLE to reference the PDF page
4. **Build footer with page addresses**
5. **Validate generated file with parser**

### Empty Layer Data

For a blank MAINLAYER (no strokes), use RATTA_RLE encoding:
```python
# Minimal empty layer - all transparent
empty_layer = bytes([0x62, 0xff] * (width * height // 0x4000))
```

---

## File Validation

After creating a .note file, validate it:

```python
import io
from supernotelib.parser import SupernoteXParser

stream = io.BytesIO(generated_binary)
parser = SupernoteXParser()
metadata = parser.parse_stream(stream)
# If no exception, file is valid
```

---

## References

- supernotelib: https://github.com/jya-dev/supernote-tool
- Apache License 2.0

---

## Appendix: Sample Hex Dump (First 512 bytes)

```
00000000: 6e6f 7465 534e 5f46 494c 455f 5645 525f  noteSN_FILE_VER_
00000010: 3230 3233 3030 3135 9201 0000 3c4d 4f44  20230015....<MOD
00000020: 554c 455f 4c41 4245 4c3a 6e6f 6e65 3e3c  ULE_LABEL:none><
00000030: 4649 4c45 5f54 5950 453a 4e4f 5445 3e3c  FILE_TYPE:NOTE><
00000040: 4150 504c 595f 4551 5549 504d 454e 543a  APPLY_EQUIPMENT:
00000050: 4e35 3e3c 4649 4e41 4c4f 5045 5241 5449  N5><FINALOPERATI
00000060: 4f4e 5f50 4147 453a 333e 3c46 494e 414c  ON_PAGE:3><FINAL
00000070: 4f50 4552 4154 494f 4e5f 4c41 5945 523a  OPERATION_LAYER:
00000080: 313e 3c44 4556 4943 455f 4450 493a 303e  1><DEVICE_DPI:0>
00000090: 3c53 4f46 545f 4450 493a 303e 3c46 494c  <SOFT_DPI:0><FIL
000000a0: 455f 5041 5253 455f 5459 5045 3a30 3e3c  E_PARSE_TYPE:0><
000000b0: 5241 5454 415f 4554 4d44 3a30 3e3c 4150  RATTA_ETMD:0><AP
000000c0: 505f 5645 5253 494f 4e3a 303e 3c46 494c  P_VERSION:0><FIL
000000d0: 455f 4944 3a46 3230 3235 3039 3138 3133  E_ID:F2025091813
000000e0: 3439 3333 3935 3531 3635 3165 4453 4770  49339551651eDSGp
000000f0: 5167 6c4e 5675 3e3c 4649 4c45 5f52 4543  QglNVu><FILE_REC
00000100: 4f47 4e5f 5459 5045 3a31 3e3c 4649 4c45  OGN_TYPE:1><FILE
00000110: 5f52 4543 4f47 4e5f 4c41 4e47 5541 4745  _RECOGN_LANGUAGE
00000120: 3a65 6e5f 5553 3e3c 5044 4653 5459 4c45  :en_US><PDFSTYLE
00000130: 3a6e 6f6e 653e 3c50 4446 5354 594c 454d  :none><PDFSTYLEM
00000140: 4435 3a30 3e3c 5354 594c 4555 5341 4745  D5:0><STYLEUSAGE
00000150: 5459 5045 3a30 3e3c 4849 4748 4c49 4748  TYPE:0><HIGHLIGH
00000160: 5449 4e46 4f3a 303e 3c48 4f52 495a 4f4e  TINFO:0><HORIZON
00000170: 5441 4c5f 4348 4543 4b3a 303e 3c49 535f  TAL_CHECK:0><IS_
00000180: 4f4c 445f 4150 504c 595f 4551 5549 504d  OLD_APPLY_EQUIPM
00000190: 454e 543a 313e 3c41 4e54 4941 4c49 4153  ENT:1><ANTIALIAS
000001a0: 494e 475f 434f 4e56 4552 543a 323e ...   ING_CONVERT:2>...
```

Note: Bytes 0x18-0x1B contain the header block length (little-endian).
