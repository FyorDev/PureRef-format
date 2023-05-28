import os
import struct
import colorsys
from .items import PurImage, PurGraphicsImageItem, PurGraphicsTextItem

########################################################################################################################
# The class this whole project is about
# Build an interpreter for this class to make your own PureRef converter to/from
# any file format without having to decipher the hex bytes like I had to
########################################################################################################################


class PurFile:

    # A class holding all the images (which include their own transforms),
    # text and anything else that would be in a .pur file
    # Can be exported to a .pur file, can be imported from a .pur file and can be generated from images to later export
    def __init__(self):
        self.canvas = [-10000.0, -10000.0, 10000.0, 10000.0]  # Canvas width and height
        self.zoom = 1.0  # View zoom level
        self.xCanvas, self.yCanvas = 0, 0  # View location
        self.folderLocation = os.getcwd()
        self.images = []  # image list
        self.text = []  # text list

    def count_image_items(self):
        # Count the amount of image transforms and assign their IDs
        count = 0
        for image in self.images:
            for transform in image.transforms:
                transform.id = count
                count += 1
        return count

    def count_text_items(self, offset):  # Text IDs start after image IDs (offset)
        # Count the amount of text transforms and assign their IDs
        count = 0

        def count_children(text):
            nonlocal count

            text.id = count + offset
            for child in text.textChildren:
                count_children(child)

        for text in self.text:
            count_children(text)

        return len(self.text)  # the header only wants to know direct children

    # Import a .pur file into this object
    def read(self, file: str):
        pur_bytes = bytearray(open(file, "rb").read())
        read_pin = 0
        total_image_items = 0
        image_items = []

        def erase(length):  # Remove n bytes from bytearray
            pur_bytes[0:length] = []
            nonlocal read_pin
            read_pin += length

        def unpack(typ: str, begin: int, stop: int):  # Bytes to type
            return struct.unpack(typ, pur_bytes[begin:stop])[0]

        def unpack_erase(typ: str):  # Unpack typ and remove from pur_bytes
            val = unpack(typ, 0, struct.calcsize(typ))
            erase(struct.calcsize(typ))
            return val

        def unpack_matrix():  # Unpack and delete a matrix
            matrix = [unpack(">d", 0, 8),
                      unpack(">d", 8, 16),
                      unpack(">d", 24, 32),
                      unpack(">d", 32, 40)]

            erase(48)
            return matrix

        def unpack_rgb():
            rgb = [unpack_erase(">H"),
                   unpack_erase(">H"),
                   unpack_erase(">H")]
            return rgb

        def hsv_to_rgb(hsv):
            rgb = list(colorsys.hsv_to_rgb(hsv[0]/35900, hsv[1]/65535, hsv[2]/65535))
            rgb = [int(i*65535) for i in rgb]
            return rgb

        def unpack_string():
            length = unpack_erase(">I")
            string = pur_bytes[0:length].decode("utf-16-be", errors="replace")
            erase(length)
            return string

        def read_header():
            # total_text_items = unpack('>H', 12, 14) - unpack('>H', 14, 16)
            nonlocal total_image_items
            total_image_items = unpack('>H', 14, 16)
            # file_length = unpack('>Q', 16, 24])

            # Canvas width and height
            self.canvas = [
                unpack('>d', 112, 120),
                unpack('>d', 120, 128),
                unpack('>d', 128, 136),
                unpack('>d', 136, 144)
            ]
            self.zoom = unpack('>d', 144, 152)
            self.xCanvas, self.yCanvas = unpack('>i', 216, 220), unpack('>i', 220, 224)

            # Done reading header, remove and update readPin
            erase(224)

        def read_images():
            png_head = bytearray([137, 80, 78, 71, 13, 10, 26, 10])  # PNG header
            png_foot = bytearray([0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130])  # PNG footer

            # Read all original images, and any duplicates/links along the way
            while pur_bytes.__contains__(png_head):

                start = pur_bytes.find(png_head)
                end = pur_bytes.find(png_foot) + 12

                if start >= 4:  # There is a duplicate before the next original image
                    image_add = PurImage()
                    image_add.address = [read_pin, 4 + read_pin]
                    image_add.pngBinary = pur_bytes[0: 4]
                    self.images.append(image_add)

                    erase(4)
                else:
                    image_add = PurImage()
                    image_add.address = [start + read_pin, end + read_pin]
                    image_add.pngBinary = pur_bytes[start: end]
                    self.images.append(image_add)

                    erase(end)

            # Put duplicate images IDs in images too for later sorting
            # (duplicates = totalImageItems - images.count)
            # pngBinary here is not an actual PNG but the 4 byte ID of the transform that does have the PNG
            # after transforms are put in their images by address we can merge the duplicates
            for _ in range(total_image_items - len(self.images)):
                image_add = PurImage()
                image_add.address = [read_pin, 4 + read_pin]
                image_add.pngBinary = pur_bytes[0: 4]
                self.images.append(image_add)

                erase(4)

        def read_items():
            graphics_image_item = 34
            graphics_text_item = 32

            def unpack_graphics_text_item():

                transform_end = unpack(">Q", 0, 8)  # End address of either image or text transform

                text_transform = PurGraphicsTextItem()
                erase(12 + unpack(">I", 8, 12))  # Remove textItem standard text

                text_transform.text = unpack_string()  # Read the text

                text_transform.matrix = unpack_matrix()  # Time for matrix for scaling & rotation
                text_transform.x = unpack_erase(">d")  # Location
                text_transform.y = unpack_erase(">d")

                erase(8)  # text unknown permanent 1.0 float we don't want

                text_transform.id = unpack_erase(">I")
                text_transform.zLayer = unpack_erase(">d")  # Z layer

                # Foreground color
                is_hsv = unpack_erase('>b') == 2  # byte indicating RGB or HSV
                text_transform.opacity = unpack_erase(">H")  # Opacity
                text_transform.rgb = unpack_rgb()  # RGB
                if is_hsv:
                    text_transform.rgb = hsv_to_rgb(text_transform.rgb)

                erase(2)  # Unknown 2 bytes

                # Background color
                is_background_hsv = unpack_erase(">b") == 2  # Byte indicating RGB or HSV, this is really stupid
                text_transform.opacityBackground = unpack_erase(">H")  # BackgroundOpacity
                text_transform.rgbBackground = unpack_rgb()  # BackgroundRGB
                if is_background_hsv:
                    text_transform.rgbBackground = hsv_to_rgb(text_transform.rgbBackground)

                number_of_children = unpack(">I", 2, 6)

                erase(transform_end - read_pin)

                if number_of_children > 0:
                    add_text_children(text_transform, number_of_children)

                return text_transform

            def add_text_children(parent, number_of_children):
                for _ in range(number_of_children):
                    text = unpack_graphics_text_item()
                    parent.textChildren.append(text)

            # Read all GraphicsImageItems and GraphicsTextItems, they are in the order they were added
            while unpack(">I", 8, 12) == graphics_image_item or unpack(">I", 8, 12) == graphics_text_item:

                if unpack(">I", 8, 12) == graphics_image_item:

                    transform_end = unpack(">Q", 0, 8)  # End address of either image or text transform

                    transform = PurGraphicsImageItem()
                    erase(12 + unpack(">I", 8, 12))  # Remove imageItem standard text

                    brute_force_loaded = False
                    if unpack(">I", 0, 4) == 0:  # Check if bruteforceloaded
                        brute_force_loaded = True
                        erase(4)
                        print("BruteForceLoad")

                    if unpack(">i", 0, 4) == -1:  # Read&Remove source
                        erase(4)
                    else:
                        transform.source = unpack_string()

                    if not brute_force_loaded:  # Read&Remove name
                        if unpack(">i", 0, 4) == -1:
                            erase(4)
                        else:
                            transform.name = unpack_string()

                    erase(8)  # Unknown permanent 1.0 float we don't want

                    transform.matrix = unpack_matrix()  # Scaling and rotation matrix
                    transform.x = unpack_erase(">d")  # Location
                    transform.y = unpack_erase(">d")

                    erase(8)  # Second unknown permanent 1.0 float we don't want

                    transform.id = unpack_erase(">I")
                    transform.zLayer = unpack_erase(">d")
                    transform.matrixBeforeCrop = unpack_matrix()  # Time for matrixBeforeCrop for scaling & rotation
                    transform.xCrop = unpack_erase(">d")  # Location before crop
                    transform.yCrop = unpack_erase(">d")
                    transform.scaleCrop = unpack_erase(">d")  # Finally crop scale

                    # Points of crop
                    # Why are there n+1? No idea but the first seems to be a copy of the last, maybe it's offset
                    point_count = unpack_erase(">I")
                    transform.points = [[], []]

                    for _ in range(point_count):
                        erase(4)
                        transform.points[0].append(unpack_erase(">d"))
                        transform.points[1].append(unpack_erase(">d"))

                    number_of_children = (unpack(">I", 21, 25))

                    erase(transform_end - read_pin)  # Remove any bytes left in the transform

                    add_text_children(transform, number_of_children)

                    image_items.append(transform)

                elif unpack(">I", 8, 12) == graphics_text_item:

                    text = unpack_graphics_text_item()
                    self.text.append(text)

                else:
                    print("Error! Unknown item")  # Maybe more items will be added in the future
                    break

        ################################################################################################################
        # Read the PureRef file
        ################################################################################################################

        read_header()  # Read header info, set total_image_items and self.canvas

        read_images()  # Read all PNG image data, and duplicates (which are the transform.id from another image)

        read_items()  # Read all the items, and add them to the image_items list

        # After the final item, the header file_length is reached. This marks the beginning of the location and refs
        self.folderLocation = unpack_string()

        # From now on the rest of the file is just a list coupling transform IDs (GraphicsImageItem)
        # with the address of the image (PurImage) it uses. Duplicate images are included and are removed later.
        for _ in range(total_image_items):  # Put transforms in their image
            red_id = unpack(">I", 0, 4)
            ref_address = [unpack(">Q", 4, 12), unpack(">Q", 12, 20)]
            for item in image_items:
                if red_id == item.id:
                    for image in self.images:
                        if ref_address[0] == image.address[0]:
                            image.transforms = [item]

            erase(20)

        # Image is duplicate if it has 4 bytes (transform.id) but it is not all 0xFF meaning an image link
        def is_duplicate(img):
            return len(img.pngBinary) == 4 and img.pngBinary != b'\xFF\xFF\xFF\xFF'

        # Remove all duplicate images, and add their transform to the original image.
        # Duplicate images only have 4 bytes of pngBinary, which is actually the transform.id of the original image
        # We need to determine if pngBinary of an image is 4 bytes (meaning it's not image data but a transform ID,
        # and if it is, remove it and add its transform to the original image
        for image in self.images:  # Remove duplicate images and add their transform to the original image
            if is_duplicate(image):
                for other_image in self.images:
                    if struct.unpack('>I', image.pngBinary)[0] == other_image.transforms[0].id:
                        other_image.transforms += image.transforms
        # duplicates get removed, but links stay
        self.images = [image for image in self.images if not is_duplicate(image)]

    # Export this object to a .pur file
    def write(self, file: str):
        pur_bytes = bytearray()
        references = []
        text_items = 0

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
            nonlocal text_items
            pur_bytes = bytearray(b'\x00') * 224  # 224 empty bytes to fill the header with
            pur_bytes[0:4] = struct.pack(">I", 8)  # Needed to recognize the file as a PureRef file
            pur_bytes[4:12] = "1.10".encode("utf-16-be")  # Version, 1.11.1 still uses 1.10 format

            # Write GraphicsImageItem+GraphicsTextItem count and GraphicsImageItem count
            image_items = self.count_image_items()  # Assign IDs to image items
            text_items = self.count_text_items(image_items)  # Assign IDs to text items
            pur_bytes[12:14] = struct.pack(">H", image_items + text_items)
            pur_bytes[14:16] = struct.pack(">H", image_items)

            pur_bytes[24:28] = struct.pack(">I", 12)  # Unknown, needed for valid header
            pur_bytes[40:44] = struct.pack(">I", 64)  # Unknown, needed for valid header

            # Write (and assign) GraphicsImageItem ID count, not usually the same, but we discard unused transform IDs
            pur_bytes[108:112] = struct.pack(">I", image_items + text_items)

            # Write canvas width and height
            pur_bytes[112:144] = (
                struct.pack(">d", self.canvas[0]) +
                struct.pack(">d", self.canvas[1]) +
                struct.pack(">d", self.canvas[2]) +
                struct.pack(">d", self.canvas[3])
            )

            pur_bytes[144:152] = struct.pack(">d", self.zoom)  # Write canvas view zoom
            pur_bytes[176:184] = struct.pack(">d", self.zoom)  # you want x and y zoom to be the same

            pur_bytes[208:216] = struct.pack(">d", 1.0)  # Zoom multiplier, should always be 1.0

            pur_bytes[216:224] = struct.pack(">i", self.xCanvas) + struct.pack(">i", self.yCanvas)  # Canvas view X Y

        def write_images():
            nonlocal pur_bytes
            nonlocal references

            for image_add in self.images:
                image_add.address[0] = len(pur_bytes)
                pur_bytes += image_add.pngBinary
                image_add.address[1] = len(pur_bytes)

            # Create references including duplicates
            for image_add in self.images:
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

        def write_text(text_transform):
            nonlocal pur_bytes
            nonlocal text_items
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
            write_text_children(text_transform)

        def write_text_children(item):
            nonlocal text_items
            for text_child in item.textChildren:
                write_text(text_child)
                text_items += 1

        def write_image(transform):
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

        def write_items():
            nonlocal references
            nonlocal text_items

            if len(self.images) > 0:
                # Sort all imagetransforms and references by the order in which they appear in memory
                transforms_ordered = []
                for image in self.images:
                    for transform in image.transforms:
                        transforms_ordered.append(transform)
                # Sort images transforms by addresses too
                references_zip = zip(references, transforms_ordered)
                references_zip = sorted(references_zip, key=lambda x: x[0][1])
                references, transforms_ordered = map(list, zip(*references_zip))

                for transform in transforms_ordered:
                    write_image(transform)

                    # Write text children of image
                    write_text_children(transform)

            # Time for unparented text
            for textTransform in self.text:
                write_text(textTransform)

        ################################################################################################################
        # Write the PureRef file
        ################################################################################################################

        write_header()  # Write header

        write_images()  # Write images, saving addresses and references, and write duplicate images

        write_items()  # Write image and text items, in the right order

        pack_add_string(os.getcwd())  # Length location
        pur_bytes[16:24] = struct.pack(">Q", len(pur_bytes))  # Update header file_length, which is where refs begin

        # Write references which couple image addresses to transform IDs
        for reference in references:
            pack_add(">I", reference[0])
            pack_add(">Q", reference[1])
            pack_add(">Q", reference[2])

        with open(file, "wb") as f:
            f.write(pur_bytes)
