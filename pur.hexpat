#pragma author fyor
#pragma description pureref .pur files

#pragma endian big

import std.io;
import std.string;
import std.mem;
import type.size;

struct matrix {
  double m11;
  double m12;
  padding[8]; // m13, stored but rewritten as 0 by PureRef
  double m21;
  double m22;
  padding[8]; // m23, likewise
};

struct color {
  u8 rgb_or_hsv;
  u16 opacity;
  u16 r;
  u16 g;
  u16 b;
};

struct crop_point {
  padding[4];
  double x;
  double y;
};

struct header {
  std::string::SizedString<u32> version;
  u16 total_items;
  be u16 num_images;
  u64 file_length;
  // The application that wrote the file: "1.10.4" or "1.11.1", six characters
  // in twelve bytes. PureRef accepts it zero-filled, which is why it looked
  // required: the leading 0000000C is the QString's byte count.
  std::string::SizedString<u32> application_version;
  u32 checksum_length; // 64
  u8 checksum[64];
  u32 id_counter;

  double p1x;
  double p1y;
  double p2x;
  double p2y;

  double zoomX;
  padding[24];
  double zoomY;
  padding[24];
  double zoomFactor; // 1.0
  s32 viewX;
  s32 viewY;
};

fn get_end() {
  u128 png_start = std::mem::find_sequence_in_range(0, $, std::mem::size(), 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A);
  u128 png_end = 8 + std::mem::find_sequence_in_range(0, $, std::mem::size(), 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82);
  if (png_start == $) {
    return png_end - png_start;
  }
  return 4;
};


struct image {
  if (get_end() == 4) {
    // FF FF FF FF is a linked image, loaded from the item's source path;
    // anything else is the id of the item that owns the preceding PNG.
    u8 duplicate_or_link[4] [[comment("Instance of the previous image, or FFFFFFFF for a link")]];
  } else {
    u8 image[get_end()] [[comment("PNG image")]];
  }
};

struct item {
  u64 end_address;
  u32 string_length;
  char type_string[string_length];
  if (string_length == 32) // Text
  {
    std::string::SizedString<u32> text;
    matrix Matrix;
    double x;
    double y;
    padding[8];
    u32 id;
    double z;
    color foreground; 
    padding[2];
    color background;
    padding[2];
    u32 children;
    item Children[children];
  }
  else if (string_length == 34) // Image
  {
    if (std::mem::read_unsigned($, 4, 0) == 0) {
      u32 bruteForceLoaded;
    }

    if (std::mem::read_signed($, 4, 0) == -1) {
      s32 no_source;
    }
    else {
      std::string::SizedString<u32> source;
    }
    if (std::mem::read_signed($, 4, 0) == -1) {
      u32 no_name;
    }
    else {
      std::string::SizedString<u32> name;
    }
    double opacity; // 1.0 when fully opaque; PureRef keeps it as a float
    matrix Matrix;
    double x;
    double y;
    padding[8];
    u32 id;
    double z;
    matrix MatrixBeforeCrop;
    double cropX;
    double cropY;
    double cropScale;
    
    u32 point_count;
    crop_point cropPoints[point_count];
    // Stored state PureRef hands back unchanged; it writes 0.0, 1, 0, 2000, 2000
    // and normalises the u8 to a boolean. None of it affects rendering.
    double unknown_zero;
    u32 unknown_one;
    u8 unknown_flag;
    u32 unknown_2000_a;
    u32 unknown_2000_b;
    u32 children;
    item Children[children];
  }
  else
  {
    stc::error("Unknown type: {}", type);
  }
  if ($ != end_address) {
    std::print("Error: Expected to be at end address, but at {}", $);
    padding[end_address - $];
  }
};

struct pureref {
  header Header;
  image Images[Header.num_images];
  item Items[Header.total_items];
  

  std::print("$: {}", $);
  std::print("Base: {}", std::mem::base_address());
  std::print("Total length: {}", std::mem::size());
};

be pureref Pureref @ 0x00;

