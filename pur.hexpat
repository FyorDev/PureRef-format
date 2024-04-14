#pragma author Fyor
#pragma description Pureref .pur files

#pragma endian big

import std.io;
import std.string;

struct matrix {
  double matrix_val1;
  double matrix_val2;
  double matrix_val3;
  double matrix_val4;
};

struct header {
  std::string::SizedString<u32> version;
  u16 total_items;
  u16 num_images;
  u64 file_length;
  u8 unknown_required[8]; // Required 0000000C0031002E
  padding[8]; // Not required
  padding[4]; // Not required
  u8 checksum[64];
  u32 id_counter;
  matrix matrix; // -1000 -1000 1000 1000
  double zoomX;
  padding[24];
  double zoomY;
  padding[24];
  double zoomFactor; // 1.0
  s32 viewX;
  s32 viewY;
};

header header @ 0x00;
std::print("{}", header.version);
