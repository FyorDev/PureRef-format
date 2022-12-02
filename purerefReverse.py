import os
import struct
import colorsys


# Similar to image transform, but this carries its own content (text)
class PurGraphicsTextItem:
    # Part of a PureRefObj

    def __init__(self):
        self.text = ""  # ASCII text contents
        self.matrix = [1.0, 0.0, 0.0, 1.0]
        self.x, self.y = 0.0, 0.0
        self.zLayer = 1.0
        self.id = 0
        self.opacity = 65535
        self.rgb = [65535, 65535, 65535]
        self.opacityBackground = 5000
        self.rgbBackground = [0, 0, 0]


# Encoding needed for all PureRef strings to work
# I don't know what exactly they're using, but at least this will work for ASCII characters
def encodestr(s: str):
    length = len(s)*2
    return (s.encode("utf-16-le")[length-1:length] + s.encode("utf-16-le")[0:length-1]).decode("utf-8")


class PurGraphicsImageItem:
    # Part of a PurImage
    # Be aware: PureRef transforms have an alternative second format for
    # rotated cropping where the image is no longer a rectangle

    def __init__(self):
        self.source = encodestr("BruteForceLoaded")
        self.name = encodestr("image")
        self.matrix = [1.0, 0.0,
                       0.0, 1.0]

        self.x, self.y = 0.0, 0.0
        self.id = 0
        self.zLayer = 1.0

        self.matrixBeforeCrop = [1.0, 0.0,
                                 0.0, 1.0]

        self.xCrop, self.yCrop = 0.0, 0.0
        self.scaleCrop = 1.0
        self.pointCount = 5  # 4 byte
        self.points = [[-1000, 1000, 1000, -1000, -1000],
                       [-1000, -1000, 1000, 1000, -1000]]  # 4 byte 01 and 2 doubles

    def reset_crop(self, width, height):
        self.xCrop, self.yCrop = -float(width/2), -float(height/2)
        w = width/2
        h = height/2
        self.points = [[-w, w, w, -w, -w],
                       [-h, -h, h, h, -h]]

    def set_source(self, source):
        self.source = encodestr(source)

    def set_name(self, name):
        self.name = encodestr(name)


class PurImage:
    # Part of a PureRefObj
    # Holds an image and its transform(s) (usually only one)
    def __init__(self):
        # original location for identification
        self.address = [0, 0]
        # image data
        self.pngBinary: bytearray = bytearray()
        # transforms[] for multiple instances
        self.transforms = []


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
        # Canvas width and height
        self.canvas = [-10000.0, -10000.0, 10000.0, 10000.0]
        # View zoom level
        self.zoom = 1.0
        # View location
        self.xCanvas, self.yCanvas = 0, 0

        self.folderLocation = encodestr(os.getcwd())

        # image list
        self.images = []
        # text list
        self.text = []

    def count_image_items(self):
        # Count the amount of image transforms and assign their IDs
        count = 0
        for image in self.images:
            for transform in image.transforms:
                transform.id = count
                count += 1
        return count

    # Import a .pur file into this object
    def read(self, file: str):
        pur_bytes = bytearray(open(file, "rb").read())

        total_text_items = struct.unpack('>H', pur_bytes[12:14])[0] - struct.unpack('>H', pur_bytes[14:16])[0]
        total_image_items = struct.unpack('>H', pur_bytes[14:16])[0]
        # file_length = struct.unpack('>Q', pur_bytes[16:24])[0]

        # Canvas width and height
        self.canvas = [
            struct.unpack('>d', pur_bytes[112:120])[0],
            struct.unpack('>d', pur_bytes[120:128])[0],
            struct.unpack('>d', pur_bytes[128:136])[0],
            struct.unpack('>d', pur_bytes[136:144])[0],
        ]
        self.zoom = struct.unpack('>d', pur_bytes[144:152])[0]
        self.xCanvas, self.yCanvas = struct.unpack('>i', pur_bytes[216:220])[0], struct.unpack('>i', pur_bytes[220:224])[0]

        # Done reading header, remove and update readPin
        read_pin = 0

        def erase(length):
            pur_bytes[0:length] = []
            nonlocal read_pin
            read_pin += length

        erase(224)

        # Read all original images, and any duplicates along the way
        while pur_bytes.__contains__(bytearray([137, 80, 78, 71,   13, 10, 26, 10])):
            start = pur_bytes.find(bytearray([137, 80, 78, 71,   13, 10, 26, 10]))
            end = pur_bytes.find(bytearray([0, 0, 0, 0,   73, 69, 78, 68,   174, 66, 96, 130])) + 12
            if start >= 4:  # There is a duplicate before the next original image
                image = PurImage()
                image.address = [read_pin, 4+read_pin]
                image.pngBinary = pur_bytes[0: 4]
                self.images.append(image)

                erase(4)
            else:
                image = PurImage()
                image.address = [start+read_pin, end+read_pin]
                image.pngBinary = pur_bytes[start: end]
                self.images.append(image)

                erase(end)

        # Put duplicate images IDs in images too for later sorting
        # (duplicates = totalImageItems - images.count)
        # pngBinary here is not an actual PNG but the 4 byte ID of the transform that does have the PNG
        # after transforms are put in their images by address we can merge the duplicate transforms into the real images
        for i in range(total_image_items - len(self.images)):
            image = PurImage()
            image.address = [read_pin, 4+read_pin]
            image.pngBinary = pur_bytes[0: 4]
            self.images.append(image)

            erase(4)

        image_items = []
        ###
        #
        # Read all GraphicsImageItems and GraphicsTextItems, they are in the order they were added
        #
        ###
        while struct.unpack(">I", pur_bytes[8:12])[0] == 34 or struct.unpack(">I", pur_bytes[8:12])[0] == 32:
            if struct.unpack(">I", pur_bytes[8:12])[0] == 34:
                transform_end = struct.unpack(">Q", pur_bytes[0:8])[0]
                transform = PurGraphicsImageItem()
                if struct.unpack(">I", pur_bytes[8:12])[0] != 34:
                    print("Read Error! expected GraphicsImageItem")

                # Remove imageItem standard text
                erase(12 + struct.unpack(">I", pur_bytes[8:12])[0])

                # Check if bruteforceloaded
                brute_force_loaded = False
                if struct.unpack(">I", pur_bytes[0:4])[0] == 0:
                    brute_force_loaded = True
                    erase(4)
                    print("BruteForceLoad")

                # Read&Remove source
                if struct.unpack(">i", pur_bytes[0:4])[0] == -1:
                    erase(4)
                else:
                    transform.source = pur_bytes[4:4 + struct.unpack(">I", pur_bytes[0:4])[0]].decode("utf-8", errors="replace")
                    erase(4 + struct.unpack(">I", pur_bytes[0:4])[0])

                # Read&Remove name
                if not brute_force_loaded:
                    if struct.unpack(">i", pur_bytes[0:4])[0] == -1:
                        erase(4)
                    else:
                        transform.name = pur_bytes[4:4 + struct.unpack(">I", pur_bytes[0:4])[0]].decode("utf-8", errors="replace")
                        erase(4 + struct.unpack(">I", pur_bytes[0:4])[0])

                # Unknown permanent 1.0 float we don't want
                if struct.unpack('>d', pur_bytes[0:8])[0] != 1.0:
                    print("Notice: mysterious permanent float is not 1.0 (investigate?) ", struct.unpack('>d', pur_bytes[0:8])[0])
                erase(8)

                # Time for matrix for scaling & rotation
                transform.matrix[0] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.matrix[1] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)
                transform.matrix[2] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.matrix[3] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)

                # Location
                transform.x = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.y = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)

                # Second unknown permanent 1.0 float we don't want
                if struct.unpack('>d', pur_bytes[0:8])[0] != 1.0:
                    print("Notice: mysterious permanent float2 is not 1.0 (investigate?) ", struct.unpack('>d', pur_bytes[0:8])[0])
                erase(8)

                # ID and Zlayer
                transform.id = struct.unpack(">I", pur_bytes[0:4])[0]
                transform.zLayer = struct.unpack(">d", pur_bytes[4:12])[0]
                erase(12)

                # Time for matrixBeforeCrop for scaling & rotation
                transform.matrixBeforeCrop[0] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.matrixBeforeCrop[1] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)
                transform.matrixBeforeCrop[2] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.matrixBeforeCrop[3] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)

                # Location before crop
                transform.xCrop = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                transform.yCrop = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)

                # Finally crop scale
                transform.scaleCrop = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)

                #
                # Points of crop
                #
                # Why are there n+1? No idea but the first seems to be a copy of the last, maybe it's offset
                #
                point_count = struct.unpack(">I", pur_bytes[0:4])[0]
                erase(4)

                points_replace = [[], []]
                for i in range(point_count):
                    points_replace[0].append(struct.unpack('>d', pur_bytes[4:12])[0])
                    points_replace[1].append(struct.unpack('>d', pur_bytes[12:20])[0])
                    erase(20)
                transform.points = points_replace

                erase(transform_end - read_pin)

                image_items.append(transform)

            #
            # Text item
            #
            elif struct.unpack(">I", pur_bytes[8:12])[0] == 32:
                text_end = struct.unpack(">Q", pur_bytes[0:8])[0]

                text_transform = PurGraphicsTextItem()
                if struct.unpack(">I", pur_bytes[8:12])[0] != 32:
                    print("Read Error! expected GraphicsTextItem")

                # Remove textItem standard text
                erase(12 + struct.unpack(">I", pur_bytes[8:12])[0])
                # Read the text
                text_transform.text = pur_bytes[4:4 + struct.unpack(">I", pur_bytes[0:4])[0]].decode("utf-8", errors="replace")
                erase(4 + struct.unpack(">I", pur_bytes[0:4])[0])
                # Time for matrix for scaling & rotation
                text_transform.matrix[0] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                text_transform.matrix[1] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)
                text_transform.matrix[2] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                text_transform.matrix[3] = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(16)

                # Location
                text_transform.x = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)
                text_transform.y = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)

                # text unknown permanent 1.0 float we don't want
                if struct.unpack('>d', pur_bytes[0:8])[0] != 1.0:
                    print("Notice: mysterious text permanent float is not 1.0 (investigate?) ",
                          struct.unpack('>d', pur_bytes[0:8])[0])
                erase(8)

                # These have an id too
                text_transform.id = struct.unpack('>I', pur_bytes[0:4])[0]
                erase(4)

                # Z layer
                text_transform.zLayer = struct.unpack('>d', pur_bytes[0:8])[0]
                erase(8)

                # byte indicating RGB or HSV
                is_hsv = struct.unpack('>b', pur_bytes[0:1])[0] == 2
                erase(1)

                # Opacity
                text_transform.opacity = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                # RGB
                text_transform.rgb[0] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                text_transform.rgb[1] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                text_transform.rgb[2] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)

                if is_hsv:
                    text_transform.rgb = list(colorsys.hsv_to_rgb((text_transform.rgb[0]) / 35900,
                                                                  (text_transform.rgb[1]) / 65535,
                                                                  (text_transform.rgb[2]) / 65535))
                    text_transform.rgb[0] = int(text_transform.rgb[0] * 65535)
                    text_transform.rgb[1] = int(text_transform.rgb[1] * 65535)
                    text_transform.rgb[2] = int(text_transform.rgb[2] * 65535)
                # Unknown 2 bytes and is hsv byte
                is_background_hsv = struct.unpack('>b', pur_bytes[2:3])[0] == 2
                erase(3)

                # BackgroundOpacity
                text_transform.opacityBackground = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                # BackgroundRGB
                text_transform.rgbBackground[0] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                text_transform.rgbBackground[1] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)
                text_transform.rgbBackground[2] = struct.unpack('>H', pur_bytes[0:2])[0]
                erase(2)

                if is_background_hsv:
                    text_transform.rgbBackground = list(colorsys.hsv_to_rgb((text_transform.rgbBackground[0]) / 35900,
                                                                            (text_transform.rgbBackground[1]) / 65535,
                                                                            (text_transform.rgbBackground[2]) / 65535))
                    text_transform.rgbBackground[0] = int(text_transform.rgbBackground[0] * 65535)
                    text_transform.rgbBackground[1] = int(text_transform.rgbBackground[1] * 65535)
                    text_transform.rgbBackground[2] = int(text_transform.rgbBackground[2] * 65535)
                self.text.append(text_transform)
                erase(text_end - read_pin)
            else:
                print("Error! Unknown item")
                break

        #
        #   All items done!
        #   ImageItems are in ImageItems[] to link with images later
        #

        self.folderLocation = pur_bytes[4:4+struct.unpack('>I', pur_bytes[0:4])[0]].decode("utf-8")
        erase(4+struct.unpack('>I', pur_bytes[0:4])[0])

        # Put transforms in images (including empty reference images)
        for i in range(total_image_items):
            red_id = struct.unpack('>I', pur_bytes[0:4])[0]
            ref_address = [struct.unpack('>Q', pur_bytes[4:12])[0], struct.unpack('>Q', pur_bytes[12:20])[0]]
            for item in image_items:
                if red_id == item.id:
                    for image in self.images:
                        if ref_address[0] == image.address[0]:
                            image.transforms = [item]

            erase(20)

        # Put all duplicate images together
        for image in self.images:
            if len(image.pngBinary) == 4:
                for other_image in self.images:
                    if struct.unpack('>I', image.pngBinary)[0] == other_image.transforms[0].id:
                        other_image.transforms += image.transforms
        self.images = [image for image in self.images if len(image.pngBinary) != 4]

    # Export this object to a .pur file
    def write(self, file: str):
        # A standard empty header for PureRef 1.11
        pur_bytes = bytearray(b'\x00\x00\x00\x08\x00\x31\x00\x2E\x00\x31\x00\x30\x00\x00\x00\x00'
                              b'\x00\x00\x00\x00\x00\x00\x01\x2E\x00\x00\x00\x0C\x00\x31\x00\x2E'
                              b'\x00\x31\x00\x31\x00\x2E\x00\x31\x00\x00\x00\x40\x00\x35\x00\x62'
                              b'\x00\x65\x00\x62\x00\x63\x00\x32\x00\x63\x00\x66\x00\x66\x00\x33'
                              b'\x00\x31\x00\x35\x00\x31\x00\x62\x00\x31\x00\x63\x00\x30\x00\x37'
                              b'\x00\x30\x00\x34\x00\x39\x00\x64\x00\x33\x00\x65\x00\x65\x00\x61'
                              b'\x00\x65\x00\x30\x00\x36\x00\x35\x00\x35\x00\x66\x00\x00\x00\x00'
                              b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                              b'\x3F\xF0\x00\x00\x00\x00\x00\x00\x3F\xF0\x00\x00\x00\x00\x00\x00'
                              b'\x3F\xF0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                              b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                              b'\x3F\xF0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                              b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                              b'\x3F\xF0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        # Write GraphicsImageItem+GraphicsTextItem count and GraphicsImageItem count
        image_items = self.count_image_items()
        pur_bytes[12:14] = bytearray(struct.pack(">H", image_items + len(self.text)))
        pur_bytes[14:16] = bytearray(struct.pack(">H", image_items))

        # Write (and assign) GraphicsImageItem ID count, not usually the same, but we discard unused transform IDs
        pur_bytes[108:112] = bytearray(struct.pack(">I", image_items + len(self.text)))
        # ImageItems received IDs in CountImageItems(), now give text their own ID
        for i in range(len(self.text)):
            self.text[i].id = image_items + i

        # Write canvas width and height
        pur_bytes[112:144] = (
            bytearray(struct.pack(">d", self.canvas[0])) +
            bytearray(struct.pack(">d", self.canvas[1])) +
            bytearray(struct.pack(">d", self.canvas[2])) +
            bytearray(struct.pack(">d", self.canvas[3]))
        )
        # Write canvas view zoom, you want x and y zoom to be the same
        pur_bytes[144:152] = bytearray(struct.pack(">d", self.zoom))
        pur_bytes[176:184] = bytearray(struct.pack(">d", self.zoom))
        # Write canvas view X and Y
        pur_bytes[216:224] = bytearray(struct.pack(">i", self.xCanvas)) + bytearray(struct.pack(">i", self.yCanvas))

        # Add all images
        for image in self.images:
            image.address[0] = len(pur_bytes)
            pur_bytes += image.pngBinary
            image.address[1] = len(pur_bytes)

        references = []
        #
        # Create references including duplicates
        # 
        for image in self.images:
            i = 0
            parent = object
            for transform in image.transforms:
                if i == 0:
                    parent = transform
                    references.append([transform.id, image.address[0], image.address[1]])
                else:
                    references.append([transform.id, len(pur_bytes), len(pur_bytes)+4])
                    pur_bytes += bytearray(struct.pack(">i", parent.id))

                i += 1

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

        #
        # Add transforms
        #

            for transform in transforms_ordered:
                # transform_end prints current writePin for now to replace later
                transform_end = len(pur_bytes)
                pur_bytes += bytearray(struct.pack(">Q", 0))
                # Purimageitem text
                brute_force_loaded = transform.source.encode == encodestr("brute_force_loaded")
                pur_bytes += struct.pack(">I", 34)
                pur_bytes += struct.pack(">b", 0)
                pur_bytes += "GraphicsImageItem".encode("utf-16-le")
                # Is bruteforceloaded there is an extra empty 8 byte
                if brute_force_loaded:
                    pur_bytes += struct.pack(">I", 0)
                # Source
                pur_bytes[len(pur_bytes)-1:len(pur_bytes)] = struct.pack(">I", len(transform.source.encode("utf-8")))
                pur_bytes += transform.source.encode("utf-8")
                # Name (skipped if bruteforceloaded)
                # PureRef can have empty names, but we have brute_force_loaded as default
                if not brute_force_loaded:
                    pur_bytes += struct.pack(">I", len(transform.name.encode("utf-8")))
                    pur_bytes += transform.name.encode("utf-8")

                #
                # Start actual transform
                #

                # Mysterious 1.0 double
                pur_bytes += struct.pack(">d", 1.0)
                # Scaling matrix
                pur_bytes += struct.pack(">d", transform.matrix[0])
                pur_bytes += struct.pack(">d", transform.matrix[1])
                pur_bytes += struct.pack(">d", 0.0)
                pur_bytes += struct.pack(">d", transform.matrix[2])
                pur_bytes += struct.pack(">d", transform.matrix[3])
                pur_bytes += struct.pack(">d", 0.0)
                # Location
                pur_bytes += struct.pack(">d", transform.x)
                pur_bytes += struct.pack(">d", transform.y)
                # Mysterious 1.0 double
                pur_bytes += struct.pack(">d", 1.0)
                # ID and ZLayer
                pur_bytes += struct.pack(">I", transform.id)
                pur_bytes += struct.pack(">d", transform.zLayer)
                # MatrixBeforeCrop
                pur_bytes += struct.pack(">d", transform.matrixBeforeCrop[0])
                pur_bytes += struct.pack(">d", transform.matrixBeforeCrop[1])
                pur_bytes += struct.pack(">d", 0.0)
                pur_bytes += struct.pack(">d", transform.matrixBeforeCrop[2])
                pur_bytes += struct.pack(">d", transform.matrixBeforeCrop[3])
                pur_bytes += struct.pack(">d", 0.0)
                # Location before crop
                pur_bytes += struct.pack(">d", transform.xCrop)
                pur_bytes += struct.pack(">d", transform.yCrop)
                # Finally crop scale
                pur_bytes += struct.pack(">d", transform.scaleCrop)

                # Number of crop points
                pur_bytes += struct.pack(">I", len(transform.points[0]))
                for i in range(len(transform.points[0])):
                    if i == 0:
                        pur_bytes += struct.pack(">I", 0)
                    else:
                        pur_bytes += struct.pack(">I", 1)
                    pur_bytes += struct.pack(">d", transform.points[0][i])
                    pur_bytes += struct.pack(">d", transform.points[1][i])

                # No idea if this actually holds information, but it always looks the same
                pur_bytes += struct.pack(">d", 0.0)
                pur_bytes += struct.pack(">I", 1)
                pur_bytes += struct.pack(">b", 0)
                pur_bytes += struct.pack(">q", -1)
                pur_bytes += struct.pack(">I", 0)

                # Start of transform needs its own end address
                pur_bytes[transform_end:transform_end+8] = bytearray(struct.pack(">Q", len(pur_bytes)))

        #
        #   DONE image transforms loaded
        #

        # Time for text
        for textTransform in self.text:
            transform_end = len(pur_bytes)
            pur_bytes += bytearray(struct.pack(">Q", 0))

            pur_bytes[transform_end:transform_end+8] = bytearray(struct.pack(">Q", len(pur_bytes)))
            pur_bytes += struct.pack(">I", 32)
            pur_bytes += struct.pack(">b", 0)
            pur_bytes += "GraphicsTextItem".encode("utf-16-le")
            pur_bytes[len(pur_bytes)-1:len(pur_bytes)] = []
            # The text
            pur_bytes += struct.pack(">I", len(textTransform.text))
            pur_bytes += textTransform.text.encode("utf-8")

            # Matrix
            pur_bytes += struct.pack(">d", textTransform.matrix[0])
            pur_bytes += struct.pack(">d", textTransform.matrix[1])
            pur_bytes += struct.pack(">d", 0.0)
            pur_bytes += struct.pack(">d", textTransform.matrix[2])
            pur_bytes += struct.pack(">d", textTransform.matrix[3])
            pur_bytes += struct.pack(">d", 0.0)

            # Location
            pur_bytes += struct.pack(">d", textTransform.x)
            pur_bytes += struct.pack(">d", textTransform.y)
            # Mysterious 1.0 float
            pur_bytes += struct.pack(">d", 1.0)
            # ID
            pur_bytes += struct.pack(">I", textTransform.id)
            # Zlayer
            pur_bytes += struct.pack(">d", textTransform.zLayer)
            # Weird meaningless byte
            pur_bytes += struct.pack(">b", 1)
            # Opacity n RGB
            pur_bytes += struct.pack(">H", textTransform.opacity)
            pur_bytes += struct.pack(">H", textTransform.rgb[0])
            pur_bytes += struct.pack(">H", textTransform.rgb[1])
            pur_bytes += struct.pack(">H", textTransform.rgb[2])
            # Mysterious thing that counts something about background
            pur_bytes += struct.pack(">H", 0)
            pur_bytes += struct.pack(">b", 1)
            # Background opacity n RGB
            pur_bytes += struct.pack(">H", textTransform.opacityBackground)
            pur_bytes += struct.pack(">H", textTransform.rgbBackground[0])
            pur_bytes += struct.pack(">H", textTransform.rgbBackground[1])
            pur_bytes += struct.pack(">H", textTransform.rgbBackground[2])
            pur_bytes += struct.pack(">I", 0)
            pur_bytes += struct.pack(">H", 0)

            # Start of transform needs its own end address
            pur_bytes[transform_end:transform_end+8] = bytearray(struct.pack(">Q", len(pur_bytes)))

        # Location
        pur_bytes += struct.pack(">I", len(self.folderLocation))
        pur_bytes += self.folderLocation.encode("utf-8")
        pur_bytes[16:24] = bytearray(struct.pack(">Q", len(pur_bytes)))

        for reference in references:
            pur_bytes += struct.pack(">I", reference[0])
            pur_bytes += struct.pack(">Q", reference[1])
            pur_bytes += struct.pack(">Q", reference[2])

        with open(file, "wb") as f:
            f.write(pur_bytes)
