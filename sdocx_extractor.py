#!/usr/bin/env python3
"""
Samsung Notes SDOCX Data Extractor

Extracts all data from Samsung Notes .sdocx files using the Modern Format (Little-Endian).
Based on decompiled SDK analysis of classes:
- T.q (I/O primitives)
- g0.h (WNote - note.note)  
- g0.u (Page - .page files)
- g0.C1316b (Layer)
- j0.b (ObjectBase)
- j0.p (ObjectStroke)
"""

import struct
import zipfile
import json
import sys
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from io import BytesIO


class BinaryReader:
    """Little-Endian binary reader based on T.q methods from SDK."""
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
    
    def seek(self, pos: int):
        self.pos = pos
    
    def skip(self, n: int):
        self.pos += n
    
    def tell(self) -> int:
        return self.pos
    
    def remaining(self) -> int:
        return len(self.data) - self.pos
    
    def read_bytes(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise IndexError(f"Cannot read {n} bytes at position {self.pos}")
        result = self.data[self.pos:self.pos + n]
        self.pos += n
        return result
    
    def read_int32(self) -> int:
        """T.q.P() - Little-endian signed int32"""
        return struct.unpack('<i', self.read_bytes(4))[0]
    
    def read_int64(self) -> int:
        """T.q.Q() - Little-endian signed int64"""
        return struct.unpack('<q', self.read_bytes(8))[0]
    
    def read_short(self) -> int:
        """T.q.S() - Little-endian signed short"""
        return struct.unpack('<h', self.read_bytes(2))[0]
    
    def read_byte(self) -> int:
        return self.read_bytes(1)[0]
    
    def read_double(self) -> float:
        return struct.unpack('<d', self.read_bytes(8))[0]
    
    def read_string(self) -> Optional[str]:
        """T.q.U() - UTF-16LE string with short length prefix"""
        if self.remaining() < 2:
            return None
        length = self.read_short()
        if length <= 0:
            return "" if length == 0 else None
        if self.remaining() < length * 2:
            return None
        chars = []
        for _ in range(length):
            char_code = struct.unpack('<H', self.read_bytes(2))[0]
            # Handle surrogates (invalid in isolation)
            if 0xD800 <= char_code <= 0xDFFF:
                chars.append('\ufffd')  # replacement character
            else:
                chars.append(chr(char_code))
        return ''.join(chars)



# Object type constants
OBJECT_TYPE_STROKE = 1
OBJECT_TYPE_TEXTBOX_SIMPLE = 2
OBJECT_TYPE_TEXTBOX_RICH = 3
OBJECT_TYPE_CONTAINER = 4
OBJECT_TYPE_IMAGE = 7
OBJECT_TYPE_AUDIO = 8
OBJECT_TYPE_VIDEO = 10
OBJECT_TYPE_PDF = 11
OBJECT_TYPE_SHAPE = 13
OBJECT_TYPE_LINK = 14
OBJECT_TYPE_STROKE_V2 = 15
OBJECT_TYPE_FORMULA = 17
OBJECT_TYPE_SIGNATURE = 19
OBJECT_TYPE_TABLE = 20
OBJECT_TYPE_CHART = 21
OBJECT_TYPE_DRAWING = 22
OBJECT_TYPE_AI_DRAWING = 23
OBJECT_TYPE_STROKE_GROUP = 100

OBJECT_TYPE_NAMES = {
    1: "Stroke", 2: "TextBoxSimple", 3: "TextBoxRich", 4: "Container",
    7: "Image", 8: "Audio", 10: "Video", 11: "PDF", 13: "Shape",
    14: "Link", 15: "StrokeV2", 17: "Formula", 19: "Signature",
    20: "Table", 21: "Chart", 22: "Drawing", 23: "AIDrawing", 100: "StrokeGroup",
}

SUPPORTED_TYPES = [1,2,3,4,7,8,10,11,13,14,15,17,19,20,21,23]


@dataclass
class BoundingRect:
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


@dataclass
class ObjectData:
    object_type: int = 0
    object_type_name: str = ""
    uuid: str = ""
    modified_time: int = 0
    bounding_rect: BoundingRect = field(default_factory=BoundingRect)
    format_version: int = 0
    binary_size: int = 0
    stroke_data_size: int = 0
    child_count: int = 0
    children: List['ObjectData'] = field(default_factory=list)


@dataclass
class LayerData:
    uuid: str = ""
    modified_time: int = 0
    visible: bool = True
    locked: bool = False
    object_count: int = 0
    objects: List[ObjectData] = field(default_factory=list)
    hash: str = ""


@dataclass  
class PageData:
    uuid: str = ""
    modified_time: int = 0
    format_version: int = 0
    width: int = 0
    height: int = 0
    layer_count: int = 0
    layers: List[LayerData] = field(default_factory=list)


@dataclass
class NoteMetadata:
    format_version: int = 0
    note_id: str = ""
    created_time: int = 0
    modified_time: int = 0
    width: int = 0
    height: int = 0
    title: str = ""


@dataclass
class SDOCXData:
    metadata: NoteMetadata = field(default_factory=NoteMetadata)
    page_ids: List[str] = field(default_factory=list)
    pages: List[PageData] = field(default_factory=list)
    media_files: List[str] = field(default_factory=list)


class NoteNoteParser:
    """Parse note.note file based on g0.h class."""
    
    def parse(self, data: bytes) -> NoteMetadata:
        reader = BinaryReader(data)
        meta = NoteMetadata()
        
        # Header from h.b()
        offset_to_data = reader.read_int32()
        reader.skip(1)
        flags = reader.read_int32()
        reader.skip(1)
        meta_flags = reader.read_int32()
        
        meta.format_version = reader.read_int32()
        meta.note_id = reader.read_string() or ""
        reader.read_int32()  # file_revision
        meta.created_time = reader.read_int64()
        meta.modified_time = reader.read_int64()
        meta.width = reader.read_int32()
        meta.height = reader.read_int32()
        reader.read_int32()  # page_h_padding
        reader.read_int32()  # page_v_padding
        reader.read_int32()  # min_format_version
        
        # Title object
        title_size = reader.read_int32()
        if title_size > 0:
            title_data = reader.read_bytes(title_size)
            meta.title = self._extract_title(title_data)
        
        return meta
    
    def _extract_title(self, data: bytes) -> str:
        """Extract title from text object binary.
        
        The title text is stored as: int32 length, then UTF-16LE characters.
        We search for the pattern within the text object data.
        """
        if len(data) < 20:
            return ""
        
        # Search for int32 length + UTF-16LE text pattern
        # The length should be reasonable (3-200 characters)
        for i in range(0, len(data) - 10):
            potential_len = struct.unpack('<i', data[i:i+4])[0]
            if 3 <= potential_len <= 200:
                start = i + 4
                end = start + potential_len * 2
                if end <= len(data):
                    try:
                        text_bytes = data[start:end]
                        # Check if it looks like valid UTF-16LE text
                        valid = True
                        for j in range(0, len(text_bytes), 2):
                            char = struct.unpack('<H', text_bytes[j:j+2])[0]
                            # Must be printable ASCII
                            if not (0x20 <= char <= 0x7E):
                                valid = False
                                break
                        if valid:
                            return text_bytes.decode('utf-16-le')
                    except Exception:
                        continue
        
        return ""




class PageParser:
    """Parse .page files based on g0.u class."""
    
    def parse(self, data: bytes) -> PageData:
        reader = BinaryReader(data)
        page = PageData()
        
        # Header from u.f()
        layer_offset = reader.read_int32()  # iP
        reader.seek(0)
        reader.skip(4)
        reader.read_int32()  # var_data_offset (iP2)
        reader.skip(1)
        reader.read_int32()  # page_flags
        reader.skip(1)
        reader.read_int32()  # content_flags
        reader.read_int32()  # orientation
        page.width = reader.read_int32()
        page.height = reader.read_int32()
        reader.read_int32()  # offset_x
        reader.read_int32()  # offset_y
        page.uuid = reader.read_string() or ""
        page.modified_time = reader.read_int64()
        page.format_version = reader.read_int32()
        reader.read_int32()  # min_format_version
        
        # Seek to layers
        reader.seek(layer_offset)
        
        page.layer_count = reader.read_short()
        reader.read_short()  # current_layer_index
        
        for _ in range(page.layer_count):
            reader.skip(4)  # skip 4 before each layer
            layer = self._parse_layer(reader)
            page.layers.append(layer)
        
        return page
    
    def _parse_layer(self, reader: BinaryReader) -> LayerData:
        """Parse layer from u.f() - layer section."""
        layer = LayerData()
        
        reader.read_int32()  # iP8 - next offset
        reader.read_byte()   # flag 1
        flags2 = reader.read_byte()
        reader.read_byte()   # flag 3
        content_flags = reader.read_byte()  # b6
        
        layer.visible = (flags2 & 1) == 0
        layer.locked = (flags2 & 2) != 0
        
        reader.read_int32()  # c
        
        # Optional fields based on content_flags (b6)
        if content_flags & 0x01: reader.read_byte()
        if content_flags & 0x02: reader.read_int32()
        if content_flags & 0x04: reader.read_string()
        if content_flags & 0x08: layer.uuid = reader.read_string() or ""
        if content_flags & 0x10: layer.modified_time = reader.read_int64()
        if content_flags & 0x20: reader.read_int32()
        
        # Object count
        layer.object_count = reader.read_int32()
        
        # Parse objects using g() method structure
        self._parse_objects(reader, layer.object_count, layer.objects)
        
        # Layer hash (32 bytes)
        hash_bytes = reader.read_bytes(32)
        layer.hash = hash_bytes.hex()
        
        return layer
    
    def _parse_objects(self, reader: BinaryReader, count: int, out_list: List[ObjectData]):
        """Parse objects from C1316b.g() method."""
        for _ in range(count):
            obj = ObjectData()
            
            # From g(): byte b = readByte(); int iS = T.q.S();
            obj.object_type = reader.read_byte()
            obj.object_type_name = OBJECT_TYPE_NAMES.get(obj.object_type, f"Type_{obj.object_type}")
            obj.child_count = reader.read_short()  # iS - child count for containers
            
            if obj.object_type in SUPPORTED_TYPES:
                # From f(): int iP = T.q.P() - object size
                obj.binary_size = reader.read_int32()
                
                if obj.binary_size > 0 and obj.binary_size < 2097152:
                    obj_data = reader.read_bytes(obj.binary_size)
                    self._parse_object_base(obj, obj_data)
                
                # For container type, recursively parse children
                if obj.object_type == OBJECT_TYPE_CONTAINER and obj.child_count > 0:
                    self._parse_objects(reader, obj.child_count, obj.children)
            else:
                # Unknown type - skip using h() method structure
                self._skip_unknown_object(reader, obj.child_count)
            
            out_list.append(obj)
    
    def _skip_unknown_object(self, reader: BinaryReader, child_count: int):
        """Skip unknown object type using h() structure."""
        for _ in range(child_count):
            size = reader.read_int32()
            reader.read_byte()
            nested_count = reader.read_short()
            reader.skip(size)
            self._skip_unknown_object(reader, nested_count)
    
    def _parse_object_base(self, obj: ObjectData, data: bytes) -> None:
        """Parse common object header from j0.b.l() method.
        
        Structure: 
        - int32: total size (i3)
        - short: data type (must be 0)
        - int32: var_data_offset (i6)
        - byte: flag_byte_len (b)
        - short: flags (s2) within flag_byte_len bytes
        - skip remaining flag bytes
        - byte: field_byte_len
        - int32: field_flags (i12)
        - int32: format_version (i14)
        - UUID: via k0.x.a() method (short len + UTF-8 bytes)
        - long: modifiedTime
        - 4 doubles: bounding rect (left, top, right, bottom)
        - int32: timestamp (r)
        - byte: resizable (s)
        """
        if len(data) < 45:
            return
        
        try:
            reader = BinaryReader(data)
            
            # i3 = total size
            total_size = reader.read_int32()
            
            # s = data_type (must be 0)
            data_type = reader.read_short()
            if data_type != 0:
                return
            
            # i6 = var_data_offset
            var_data_offset = reader.read_int32()
            
            # b = flag_byte_len, s2 = flags
            flag_byte_len = reader.read_byte()
            flags = reader.read_short()
            # Skip remaining flag bytes
            if flag_byte_len > 2:
                reader.skip(flag_byte_len - 2)
            
            # byte: field_byte_len
            field_byte_len = reader.read_byte()
            
            # i12 = field_flags
            field_flags = reader.read_int32()
            
            # i14 = format_version
            obj.format_version = reader.read_int32()
            
            # UUID via k0.x.a() - short length then UTF-8 bytes
            uuid_len = reader.read_short()
            if uuid_len > 0 and uuid_len <= 36:
                uuid_bytes = reader.read_bytes(uuid_len)
                # Decode UTF-8, stopping at null
                try:
                    uuid_str = uuid_bytes.split(b'\x00')[0].decode('utf-8')
                    obj.uuid = uuid_str
                except:
                    obj.uuid = ""
            elif uuid_len > 36:
                # Skip if too long
                reader.skip(uuid_len)
            
            # modifiedTime (long)
            obj.modified_time = reader.read_int64()
            
            # Bounding rect (4 doubles)
            obj.bounding_rect = BoundingRect(
                left=reader.read_double(),
                top=reader.read_double(),
                right=reader.read_double(),
                bottom=reader.read_double()
            )
            
            # timestamp (int32)
            reader.read_int32()
            
            # resizable (byte)
            reader.read_byte()
            
            # Calculate remaining stroke data for stroke types
            if obj.object_type in [OBJECT_TYPE_STROKE, OBJECT_TYPE_STROKE_V2]:
                obj.stroke_data_size = len(data) - reader.tell()
        except Exception:
            pass



class PageIdInfoParser:
    def parse(self, data: bytes) -> List[str]:
        reader = BinaryReader(data)
        reader.skip(32)
        if reader.remaining() < 2:
            return []
        count = reader.read_short()
        page_ids = []
        for _ in range(count):
            if reader.remaining() < 2:
                break
            page_id = reader.read_string()
            if page_id:
                page_ids.append(page_id)
            if reader.remaining() >= 32:
                reader.skip(32)
        return page_ids


class SDOCXExtractor:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.note_parser = NoteNoteParser()
        self.page_parser = PageParser()
        self.page_id_parser = PageIdInfoParser()
    
    def extract(self) -> SDOCXData:
        result = SDOCXData()
        
        with zipfile.ZipFile(self.filepath, 'r') as zf:
            file_list = zf.namelist()
            
            if 'note.note' in file_list:
                with zf.open('note.note') as f:
                    result.metadata = self.note_parser.parse(f.read())
            
            if 'pageIdInfo.dat' in file_list:
                with zf.open('pageIdInfo.dat') as f:
                    result.page_ids = self.page_id_parser.parse(f.read())
            
            for filename in file_list:
                if filename.endswith('.page'):
                    with zf.open(filename) as f:
                        result.pages.append(self.page_parser.parse(f.read()))
            
            for filename in file_list:
                if filename.startswith('media/') and not filename.endswith('.dat'):
                    result.media_files.append(filename)
        
        return result


def count_strokes(data: SDOCXData) -> int:
    """Count all stroke objects recursively."""
    total = 0
    for page in data.pages:
        for layer in page.layers:
            total += count_strokes_in_list(layer.objects)
    return total


def count_strokes_in_list(objects: List[ObjectData]) -> int:
    count = 0
    for obj in objects:
        if obj.object_type in [OBJECT_TYPE_STROKE, OBJECT_TYPE_STROKE_V2]:
            count += 1
        if obj.children:
            count += count_strokes_in_list(obj.children)
    return count


def main():
    if len(sys.argv) < 2:
        print("Usage: python sdocx_extractor.py <path_to_sdocx>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    try:
        extractor = SDOCXExtractor(filepath)
        data = extractor.extract()
        
        output = {
            'metadata': asdict(data.metadata),
            'page_ids': data.page_ids,
            'pages': [asdict(p) for p in data.pages],
            'media_files': data.media_files,
            'summary': {
                'title': data.metadata.title,
                'page_count': len(data.pages),
                'total_layers': sum(len(p.layers) for p in data.pages),
                'total_objects': sum(sum(len(l.objects) for l in p.layers) for p in data.pages),
                'stroke_count': count_strokes(data),
            }
        }
        
        print(json.dumps(output, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
