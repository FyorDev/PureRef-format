import struct
from purformat.items import Item, PurGraphicsImageItem, PurGraphicsTextItem
from purformat.purformat import PurFile


def write_pur_file(pur_file: PurFile, filepath: str):

    pur_bytes = bytearray()
    references = []

    def pack_add(typ: str, *args):
        nonlocal pur_bytes
        pur_bytes += struct.pack(typ, *args)

    def pack_add_matrix(matrix: []):
        pack_add(">d", matrix[0])
        pack_add(">d", matrix[1])
        pack_add(">d", 0.0)
        pack_add(">d", matrix[2])
        pack_add(">d", matrix[3])
        pack_add(">d", 0.0)

    def pack_add_rgb(rgb: []):
        nonlocal pur_bytes
        for value in rgb:
            pur_bytes += struct.pack(">H", value)

    def pack_add_string(string: str):
        nonlocal pur_bytes
        pack_add(">I", len(string.encode("utf-16-be")))
        pur_bytes += string.encode("utf-16-be")

    def write_header():
        nonlocal pur_bytes
        pur_bytes = bytearray(b'\x00') * 224  # 224 empty bytes to fill the header with
        pur_bytes[0:4] = struct.pack(">I", 8)  # Needed to recognize the file as a PureRef file
        pur_bytes[4:12] = "1.10".encode("utf-16-be")  # Version, 1.11.1 still uses 1.10 format

        # Write GraphicsImageItem+GraphicsTextItem count and GraphicsImageItem count
        image_items = pur_file.count_image_items()  # Assign IDs to image items
        text_items = pur_file.count_text_items(image_items)  # Assign IDs to text items
        pur_bytes[12:14] = struct.pack(">H", image_items + text_items)
        pur_bytes[14:16] = struct.pack(">H", image_items)

        pur_bytes[24:28] = struct.pack(">I", 12)  # Unknown, needed for valid header
        pur_bytes[40:44] = struct.pack(">I", 64)  # Unknown, needed for valid header

        # Write (and assign) GraphicsImageItem ID count, not usually the same, but we discard unused transform IDs
        pur_bytes[108:112] = struct.pack(">I", image_items + text_items)

        # Write canvas width and height
        pur_bytes[112:144] = (
                struct.pack(">d", pur_file.canvas[0]) +
                struct.pack(">d", pur_file.canvas[1]) +
                struct.pack(">d", pur_file.canvas[2]) +
                struct.pack(">d", pur_file.canvas[3])
        )

        pur_bytes[144:152] = struct.pack(">d", pur_file.zoom)  # Write canvas view zoom
        pur_bytes[176:184] = struct.pack(">d", pur_file.zoom)  # you want x and y zoom to be the same

        pur_bytes[208:216] = struct.pack(">d", 1.0)  # Zoom multiplier, should always be 1.0

        pur_bytes[216:224] = struct.pack(">i", pur_file.xCanvas) + struct.pack(">i", pur_file.yCanvas)  # View X Y

    def write_images():
        nonlocal pur_bytes
        nonlocal references

        for image_add in pur_file.images:
            image_add.address[0] = len(pur_bytes)
            pur_bytes += image_add.pngBinary
            image_add.address[1] = len(pur_bytes)

        # Create references including duplicates
        for image_add in pur_file.images:
            transform_num = 0
            parent = object
            for transform_add in image_add.transforms:
                if transform_num == 0:
                    parent = transform_add
                    references.append([transform_add.id, image_add.address[0], image_add.address[1]])
                else:
                    references.append([transform_add.id, len(pur_bytes), len(pur_bytes) + 4])
                    pack_add(">i", parent.id)

                transform_num += 1

    def write_text(text_transform: PurGraphicsTextItem):
        nonlocal pur_bytes
        transform_end = len(pur_bytes)
        pur_bytes += struct.pack(">Q", 0)

        pur_bytes[transform_end:transform_end + 8] = struct.pack(">Q", len(pur_bytes))
        pack_add(">I", 32)
        pur_bytes += "GraphicsTextItem".encode("utf-16-be")

        pack_add_string(text_transform.text)  # The text

        pack_add_matrix(text_transform.matrix)  # Matrix
        pack_add(">d", text_transform.x)  # Location
        pack_add(">d", text_transform.y)

        pack_add(">d", 1.0)  # Mysterious 1.0 double

        pack_add(">I", text_transform.id)  # ID
        pack_add(">d", text_transform.zLayer)  # Zlayer

        pack_add(">b", 1)  # Weird meaningless byte

        # Foreground color
        pack_add(">H", text_transform.opacity)  # Opacity
        pack_add_rgb(text_transform.rgb)  # RGB

        pack_add(">H", 0)  # Mysterious values that counts something about background
        pack_add(">b", 1)

        # Background color
        pack_add(">H", text_transform.opacityBackground)  # Opacity
        pack_add_rgb(text_transform.rgbBackground)  # RGB

        pack_add(">H", 0)
        pack_add(">I", len(text_transform.textChildren))  # how many text children

        # Start of transform needs its own end address
        pur_bytes[transform_end:transform_end + 8] = struct.pack(">Q", len(pur_bytes))

        # Write text children
        list(map(write_text, text_transform.textChildren))

    def write_image(transform: PurGraphicsImageItem):
        nonlocal pur_bytes

        # transform_end prints current writePin for now to replace later
        transform_end = len(pur_bytes)
        pack_add(">Q", 0)
        # Purimageitem text
        brute_force_loaded = transform.source == "BruteForceLoaded"
        pack_add(">I", 34)
        pur_bytes += "GraphicsImageItem".encode("utf-16-be")
        # Is bruteforceloaded there is an extra empty 8 byte
        if brute_force_loaded:
            pack_add(">I", 0)
        # Source
        pack_add_string(transform.source)
        # Name (skipped if bruteforceloaded)
        # PureRef can have empty names, but we have brute_force_loaded as default
        if not brute_force_loaded:
            pack_add_string(transform.name)

        pack_add(">d", 1.0)  # Mysterious 1.0 double

        pack_add_matrix(transform.matrix)  # Scaling matrix
        pack_add(">d", transform.x)  # Location
        pack_add(">d", transform.y)

        pack_add(">d", 1.0)  # Mysterious 1.0 double

        pack_add(">I", transform.id)  # ID and ZLayer
        pack_add(">d", transform.zLayer)
        pack_add_matrix(transform.matrixBeforeCrop)  # MatrixBeforeCrop
        pack_add(">d", transform.xCrop)  # Location before crop
        pack_add(">d", transform.yCrop)
        pack_add(">d", transform.scaleCrop)  # Finally crop scale

        # Number of crop points
        pack_add(">I", len(transform.points[0]))
        for i in range(len(transform.points[0])):
            if i == 0:
                pack_add(">I", 0)
            else:
                pack_add(">I", 1)
            pack_add(">d", transform.points[0][i])
            pack_add(">d", transform.points[1][i])

        # Always the same, no idea if this actually holds information
        pack_add(">d", 0.0)
        pack_add(">I", 1)
        pack_add(">b", 0)
        pack_add(">q", -1)
        pack_add(">I", len(transform.textChildren))  # how many text children

        # Start of transform needs its own end address
        pur_bytes[transform_end:transform_end + 8] = struct.pack(">Q", len(pur_bytes))

        # Write text children
        list(map(write_text, transform.textChildren))

    def write_items():
        nonlocal references

        if len(pur_file.images) > 0:
            # Sort all imagetransforms and references by the order in which they appear in memory
            transforms_ordered = []
            for image in pur_file.images:
                for transform in image.transforms:
                    transforms_ordered.append(transform)
            # Sort images transforms by addresses too
            references_zip = zip(references, transforms_ordered)
            references_zip = sorted(references_zip, key=lambda x: x[0][1])
            references, transforms_ordered = map(list, zip(*references_zip))

            for transform in transforms_ordered:
                write_image(transform)

                # Write text children of image

        # Time for unparented text
        for textTransform in pur_file.text:
            write_text(textTransform)

    ################################################################################################################
    # Write the PureRef file
    ################################################################################################################

    write_header()  # Write header

    write_images()  # Write images, saving addresses and references, and write duplicate images

    write_items()  # Write image and text items, in the right order

    pack_add_string(pur_file.folderLocation)  # Length location
    pur_bytes[16:24] = struct.pack(">Q", len(pur_bytes))  # Update header file_length, which is where refs begin

    # Write references which couple image addresses to transform IDs
    for reference in references:
        pack_add(">I", reference[0])
        pack_add(">Q", reference[1])
        pack_add(">Q", reference[2])

    with open(filepath, "wb") as f:
        f.write(pur_bytes)
