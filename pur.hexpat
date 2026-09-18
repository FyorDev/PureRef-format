#pragma author fyor
#pragma description pureref .pur files

#pragma endian big

import std.io;
import std.string;
import std.mem;
import type.size;

struct matrix {
  double matrix_val1;
  double matrix_val2;
  padding[8];
  double matrix_val3;
  double matrix_val4;
  padding[8];
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
  u8 unknown_required[8]; // Required 0000000C0031002E
  padding[8]; // Not required
  padding[4]; // Not required
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
    u8 duplicate_image[4] [[comment("Duplicate of the previous image")]];
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
    u32 children;
    item Children[children];
    padding[2];
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
    padding[8];
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
    padding[21];
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

