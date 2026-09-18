#pragma author Fyor
#pragma description PureRef .pur files: the 1.10 / 1.11.1 binary format and the 2.0 / 2.1 SQLite container

// One pattern for both generations. A .pur starts with a Qt QString holding the
// format version, and that is what decides which half of this file applies:
//
//   "1.10"        the binary format, written by 1.10.x and 1.11.x alike
//   "2.0" / "2.1" a SQLite database whose first bytes were moved to the end
//
// The 2.x half reconstructs the database into its own section and offers it as
// a virtual file, so the whole scene can be opened in ImHex or any SQLite tool.
//
// Field names match pureref/v1/records.py and pureref/v2/schema.py in
// https://github.com/FyorDev/PureRef-format, which is where both layouts are
// declared once and where docs/format-v1.md and docs/format-v2.md come from.

#pragma endian big

#pragma magic [ 00 00 00 08 00 31 00 2E 00 31 00 30 ] @ 0x00
#pragma magic [ 00 00 00 06 00 32 00 2E 00 30 ] @ 0x00
#pragma magic [ 00 00 00 06 00 32 00 2E 00 31 ] @ 0x00

import std.core;
import std.io;
import std.mem;
import std.string;
import std.sys;

#ifdef __IMHEX__
    // Only ImHex itself can offer the reconstructed database as a virtual file.
    import hex.core;
#endif

// --- Qt primitives ----------------------------------------------------------

namespace qt {

    /**
        A QString: a byte count, then UTF-16BE code units. `0xffffffff` is null,
        which is not the same as empty and does appear in 1.x item records.
    */
    struct String {
        u32 length;
        if (length != 0xFFFFFFFF)
            char16 value[length / 2];
    } [[sealed, format("qt::format_string"), transform("qt::format_string")]];

    fn format_string(ref auto string) {
        if (string.length == 0xFFFFFFFF)
            return "<null>";
        if (string.length == 0)
            return "";
        return string.value;
    };

    /**
        A QByteArray: a byte count, then the bytes. `0xffffffff` is null.
    */
    struct ByteArray {
        u32 length;
        if (length != 0xFFFFFFFF)
            u8 value[length] [[color("7F5FAF")]];
    };

    /**
        The linear part of a QTransform. PureRef stores m13 and m23 and then
        ignores them: written values come back as 0, so the transform is affine.
    */
    struct Linear {
        double m11;
        double m12;
        double m13 [[comment("stored, but rewritten as 0")]];
        double m21;
        double m22;
        double m23 [[comment("stored, but rewritten as 0")]];
    };

    struct PointF {
        double x;
        double y;
    };

    struct RectF {
        double x0;
        double y0;
        double x1;
        double y1;
    };
}

// --- The 1.10 / 1.11.1 binary format ----------------------------------------

namespace legacy {

    const u32 HEADER_SIZE = 224;
    const u32 IMAGE_ITEM  = 34;      // byte length of "GraphicsImageItem"
    const u32 TEXT_ITEM   = 32;      // byte length of "GraphicsTextItem"
    const u64 PNG_SIGNATURE = 0x89504E470D0A1A0A;

    u64 referenceOffset = 0;         // where the item blocks stop

    fn is_png(u128 address) {
        return std::mem::read_unsigned(address, 8, std::mem::Endian::Big) == PNG_SIGNATURE;
    };

    /**
        True when an item block starts here: a plausible end offset followed by
        one of the two class-name lengths. This is how the image section knows
        where to stop, the same test the reader makes.
    */
    fn is_item(u128 address) {
        if (address + 12 > std::mem::size())
            return false;
        u64 end = std::mem::read_unsigned(address, 8, std::mem::Endian::Big);
        u32 marker = std::mem::read_unsigned(address + 8, 4, std::mem::Endian::Big);
        return (marker == IMAGE_ITEM || marker == TEXT_ITEM)
               && end > address && end <= std::mem::size();
    };

    struct Header {
        qt::String format_version [[comment("1.11.1 still writes 1.10 here")]];
        u16 item_count [[comment("image items plus root note items")]];
        u16 image_count;
        u64 reference_offset [[comment("where the reference table starts")]];
        qt::String application_version [[comment("1.10.4 or 1.11.1; PureRef accepts it zero-filled")]];
        qt::String checksum [[comment("MD5 hex of everything from offset 108")]];
        u32 id_count;
        qt::RectF canvas;
        double zoom;
        std::mem::Bytes<24> unknown_152 [[comment("zero in every observed file; PureRef preserves it")]];
        double zoom_y;
        std::mem::Bytes<24> unknown_184 [[comment("zero in every observed file; PureRef preserves it")]];
        double zoom_multiplier [[comment("always 1.0")]];
        s32 view_x;
        s32 view_y;

        referenceOffset = reference_offset;
        std::assert(sizeof(this) == HEADER_SIZE, "The 1.x header is 224 bytes");
    };

    /**
        A four-byte slot between the embedded PNGs: either a link marker or the
        id of the item that owns the image data in front of it.
    */
    struct Slot {
        u32 owner [[comment("0xFFFFFFFF: a linked image; otherwise the owning item's id")]];
    };

    struct Png {
        u128 tail = std::mem::find_sequence_in_range(0, $, referenceOffset,
                                                     0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82);
        std::assert(tail > $, "Embedded PNG without an IEND chunk");
        u8 data[(tail + 8) - $] [[comment("an embedded PNG, IEND included"), color("3F7F3F")]];
    } [[format("legacy::format_png")]];

    fn format_png(ref auto png) {
        return std::format("PNG, {} bytes", sizeof(png.data));
    };

    struct ImageEntry {
        if (legacy::is_png($))
            Png png [[inline]];
        else
            Slot slot [[inline]];
    };

    /**
        Image data is PNG only, found by scanning for the signature. Instances of
        the same image follow it as slots, and the reference table at the end of
        the file points at both by address.
    */
    struct ImageSection {
        ImageEntry entries[while($ < referenceOffset && !legacy::is_item($))];
    };

    struct CropPoint {
        u32 kind [[comment("0 for the first point, 1 after")]];
        double x;
        double y;
    };

    struct ImageFields {
        // Four zero bytes in front of the source mark an image PureRef recovered
        // by brute force; there is no flag for it anywhere else, and such an
        // item carries no name at all.
        bool brute_force = std::mem::read_unsigned($, 4, std::mem::Endian::Big) == 0;
        if (brute_force)
            u32 brute_force_marker [[comment("recovered by brute force")]];
        qt::String source [[comment("BruteForceLoaded for recovered images")]];
        if (!brute_force)
            qt::String name;
        double opacity [[comment("1.0 when opaque; PureRef keeps it as a float")]];
        qt::Linear linear;
        qt::PointF position [[comment("the image centre on the canvas")]];
        double constant_one [[comment("rewritten as 1.0 whatever it held")]];
        u32 id;
        double z;
        qt::Linear before_crop [[comment("the transform before cropping, for reset cropping")]];
        qt::PointF crop_offset;
        double crop_scale;
        u32 crop_point_count;
        CropPoint crop_outline[crop_point_count]
            [[comment("closed, in centred pixel coordinates: an uncropped 64x32 image spans (-32,-16)..(32,16)")]];
        std::mem::Bytes<21> tail [[comment("PureRef writes 0.0, 1, 0, 2000, 2000; kept, no observed effect")]];
        u32 children [[comment("note items nested under this image")]];
    };

    /**
        A 16-bit colour. Kind 1 is RGB and kind 2 is HSV, where the hue is scaled
        to 35900; an 8-bit channel is stored as `channel * 257`.
    */
    struct Color {
        s8 kind [[comment("1 = RGB, 2 = HSV")]];
        u16 opacity;
        u16 red;
        u16 green;
        u16 blue;
    };

    struct NoteFields {
        qt::String text [[comment("plain text; 1.x notes are not HTML")]];
        qt::Linear linear;
        qt::PointF position;
        double constant_one [[comment("rewritten as 1.0 whatever it held")]];
        u32 id;
        double z;
        Color foreground;
        std::mem::Bytes<2> colour_gap [[comment("zero in every observed file")]];
        Color background;
        std::mem::Bytes<2> tail [[comment("zero in every observed file, and it belongs before the count")]];
        u32 children;
    };

    struct Item {
        u64 end_offset [[comment("just past this item's own fields")]];
        u32 class_name_length [[comment("34 GraphicsImageItem, 32 GraphicsTextItem")]];
        char16 class_name[class_name_length / 2];
        u32 child_count = 0;
        if (class_name_length == IMAGE_ITEM) {
            ImageFields image;
            child_count = image.children;
        } else if (class_name_length == TEXT_ITEM) {
            NoteFields note;
            child_count = note.children;
        } else {
            std::error(std::format("Unknown item class length {}", class_name_length));
        }

        if ($ < end_offset)
            u8 trailing[end_offset - $] [[comment("bytes PureRef hands back unchanged"), color("7F7F7F")]];

        // Children are written after the parent's block, not nested inside it.
        Item children[child_count];
    };

    /**
        One record per image item, in address order. PureRef rejects a file whose
        ids run backwards against these addresses.
    */
    struct Reference {
        u32 id;
        u64 start [[comment("start of the image data or instance slot")]];
        u64 end;
    };

    struct File {
        Header header;
        ImageSection images;
        Item items[header.item_count];
        qt::String folder [[comment("the folder a file was last loaded from")]];
        Reference references[while($ + 20 <= std::mem::size())] @ header.reference_offset;
    };
}

// --- The 2.0 / 2.1 SQLite container -----------------------------------------

namespace modern {

    /**
        The database is `file[N:] + file[H:N]` for a header of H bytes and a
        database length of N: PureRef replaced the database's first H bytes with
        its header and appended them instead. Carving from the `SQLite format 3`
        signature therefore recovers only the displaced prefix.
    */
    struct SqliteHeader {
        char magic[16] [[comment("SQLite format 3")]];
        u16 page_size [[comment("1 means 65536")]];
        u8 write_version;
        u8 read_version;
        u8 reserved_space;
        u8 max_payload_fraction;
        u8 min_payload_fraction;
        u8 leaf_payload_fraction;
        u32 file_change_counter;
        u32 page_count;
        u32 first_freelist_page;
        u32 freelist_page_count;
        u32 schema_cookie;
        u32 schema_format;
        u32 default_page_cache_size;
        u32 largest_root_btree_page [[comment("non-zero with auto-vacuum, which PureRef enables")]];
        u32 text_encoding [[comment("1 = UTF-8")]];
        u32 user_version [[comment("PureRef's compatibility gate: 200101. A higher value is refused")]];
        u32 incremental_vacuum;
        u32 application_id [[comment("940753918 = 0x3812C3FE")]];
        u8 reserved[20];
        u32 version_valid_for;
        u32 sqlite_version_number;
    };

    /**
        The preview PureRef shows in a file dialog, as JPEG or PNG bytes. The
        same image is stored again in `metadata.thumbnail` inside the database.
    */
    struct Thumbnail {
        u32 length [[comment("0xffffffff would be a null QByteArray; PureRef writes real bytes")]];
        std::mem::Bytes<length == 0xFFFFFFFF ? 0 : length> value [[color("7F5FAF")]];
    }
    #ifdef __IMHEX__
        [[hex::visualize("image", value)]]
    #endif
    ;

    u32 pageSize = 4096;      // taken from the reconstructed database header

    /**
        A b-tree page header, so the database can be walked page by page. The
        scene itself is ordinary SQLite: seven tables, described in
        docs/format-v2.md. Open the "scene.sqlite" virtual file to query it
        rather than reading cells out of these pages by hand.
    */
    struct PageHeader {
        u8 type [[comment("2 interior index, 5 interior table, 10 leaf index, 13 leaf table")]];
        u16 first_freeblock;
        u16 cell_count;
        u16 cell_content_start [[comment("0 means 65536")]];
        u8 fragmented_free_bytes;
        if (type == 2 || type == 5)
            u32 right_child;
        u16 cell_pointers[cell_count];
    };

    struct Page {
        u128 start = $;
        // Page 1 carries the 100-byte file header before its b-tree header.
        if (std::core::array_index() == 0)
            SqliteHeader file_header;
        if (std::mem::read_unsigned($, 1) != 0)
            PageHeader page;
        else
            u8 unused_page [[comment("a freelist or overflow page")]];
        padding[pageSize - ($ - start)];
    };

    struct Header {
        qt::String format_version;
        u32 reserved;
        u64 database_size [[comment("N: the database's own length")]];
        qt::String application_version;
        qt::String checksum [[comment("MD5 of everything after this field: the thumbnail and both database halves")]];
        if (format_version != "2.0")
            Thumbnail thumbnail [[comment("JPEG or PNG preview; the 2.0 layout has no such field")]];
    };

    struct File {
        Header header;
        u128 header_size = $;
        std::assert(header.database_size >= header_size && header.database_size <= std::mem::size(),
                    "Header length and database size do not add up; the file is truncated");

        // The two halves, shown where they actually sit in the file.
        u8 moved_body[std::mem::size() - header.database_size] @ header.database_size
            [[comment("database[H:N], the part that was not displaced")]];
        u8 moved_prefix[header.database_size - header_size] @ header_size
            [[comment("database[0:H], moved here to make room for the header")]];

        std::mem::Section database = std::mem::create_section("database");
        std::mem::copy_value_to_section(moved_body, database, 0);
        std::mem::copy_value_to_section(moved_prefix, database, sizeof(moved_body));

        SqliteHeader sqlite @ 0x00 in database;
        std::assert(std::string::starts_with(sqlite.magic, "SQLite format 3"),
                    "The reconstructed prefix is not a SQLite database");
        pageSize = sqlite.page_size == 1 ? 65536 : sqlite.page_size;

        // A page map, for files small enough that mapping them is cheap.
        if (sqlite.page_count <= 512)
            Page pages[sqlite.page_count] @ 0x00 in database;
        u8 bytes[std::mem::get_section_size(database)] @ 0x00 in database [[hidden]];

        #ifdef __IMHEX__
            // Open "scene.sqlite" from the Virtual Filesystem tab, or drop it into
            // any SQLite browser: the scene lives in seven ordinary tables.
            hex::core::add_virtual_file("scene.sqlite", bytes);
        #endif
    };

    /**
        A serialized cell, for when you have a payload in front of you: the
        `transform`, `sort_order`, `image_transform`, `image_bounds`,
        `fixed_size`, `scene_rect`, `view_transform` and `strokes` columns each
        hold one of these.

        Place it by hand -- `modern::Variant v @ 0x123;` -- on a payload you
        extracted. It will not fit a raw SQLite page: those cells have storage
        class TEXT, so every payload byte above 0x7f was re-encoded as UTF-8 and
        has to be mapped back through Latin-1 first.
    */
    struct Variant {
        u32 type_id [[comment("20 QRectF, 22 QSizeF, 80 QTransform, 1024 a named custom type")]];
        u8 is_null;
        if (type_id == 1024)
            std::string::NullString type_name;
        if (type_id == 20)
            double rect[4] [[comment("x, y, width, height")]];
        else if (type_id == 22)
            double size[2] [[comment("width, height; (-1,-1) means automatic")]];
        else if (type_id == 80)
            double transform[9] [[comment("m11 m12 m13 m21 m22 m23 m31 m32 m33")]];
    };
}

// --- Whichever generation this file is --------------------------------------

struct PurFile {
    if (std::mem::read_unsigned(0x00, 4, std::mem::Endian::Big) == 8)
        legacy::File legacy [[inline]];
    else
        modern::File modern [[inline]];
};

PurFile pur @ 0x00;
