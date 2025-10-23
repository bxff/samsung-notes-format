# SDOCX Analysis Specification

## ADDED Requirements

### Requirement: SDOCX ZIP Structure Analysis
The system SHALL analyze the complete ZIP archive structure of SDOCX files to understand file organization and content relationships.

#### Scenario: Archive Content Enumeration
Given a sample SDOCX file, when opened as a ZIP archive, then the system SHALL list all contained files with their metadata (size, compression, timestamps).

#### Scenario: File Purpose Identification
Given the archive contents, when analyzed, then the system SHALL identify the purpose of each file (e.g., note.note for content, metadata files, media files).

#### Scenario: ZIP Structure Mapping
Given multiple SDOCX samples, when compared, then the system SHALL document the consistent ZIP structure and any variations across note types.

### Requirement: note.note Binary Format Analysis
The system SHALL reverse engineer the binary format of note.note files to decode the complete note content structure.

#### Scenario: Binary Header Analysis
Given a note.note file, when analyzed with hexdump, then the system SHALL identify file headers, magic numbers, and version information.

#### Scenario: Data Structure Mapping
Given the binary content, when pattern-analyzed, then the system SHALL map out the complete data structure including text, strokes, metadata, and multimedia references.

#### Scenario: Encoding Scheme Discovery
Given binary data sections, when analyzed, then the system SHALL identify character encodings, compression schemes, and any data obfuscation methods.

#### Scenario: Stroke Data Understanding
Given drawing/note content, when analyzed, then the system SHALL understand how stroke coordinates, pressure, timing, and formatting are encoded.

### Requirement: Metadata Extraction
The system SHALL extract and understand all metadata stored in SDOCX files to enable complete note property parsing.

#### Scenario: Note Property Discovery
Given sample notes, when analyzed, then the system SHALL identify how creation time, modification time, author, title, and other properties are stored.

#### Scenario: Feature Capability Detection
Given various note types (text, drawing, audio), when analyzed, then the system SHALL identify how different content types and their properties are encoded.

### Requirement: Cross-Version Compatibility Analysis
The system SHALL analyze format variations across different Samsung Notes versions to ensure compatibility understanding.

#### Scenario: Format Evolution Tracking
Given SDOCX files from different app versions, when compared, then the system SHALL document format changes, additions, and backward compatibility.

#### Scenario: Migration Path Understanding
Given format variations, when analyzed, then the system SHALL understand how to handle version differences in parsers and converters.

## MODIFIED Requirements

### Requirement: Existing Extractor Enhancement
The system SHALL enhance the existing sdocxToTxt.py based on binary analysis findings to improve extraction capabilities.

#### Scenario: Complete Content Extraction
Given detailed format understanding, when applied to existing code, then the system SHALL enhance extraction to include metadata, formatting, stroke data, and media references.

#### Scenario: Error Handling Improvement
Given edge cases discovered during analysis, when implemented, then the system SHALL improve error handling and corruption recovery.

## REMOVED Requirements

*None identified*