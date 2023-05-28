import struct
import colorsys
from .items import Item, PurImage, PurGraphicsImageItem, PurGraphicsTextItem
from .purformat import PurFile


def read_pur_file(pur_file: PurFile, filepath: str):

    pur_bytes = bytearray(open(filepath, "rb").read())
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
        rgb = list(colorsys.hsv_to_rgb(hsv[0] / 35900, hsv[1] / 65535, hsv[2] / 65535))
        rgb = [int(i * 65535) for i in rgb]
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
        pur_file.canvas = [
            unpack('>d', 112, 120),
            unpack('>d', 120, 128),
            unpack('>d', 128, 136),
            unpack('>d', 136, 144)
        ]
        pur_file.zoom = unpack('>d', 144, 152)
        pur_file.xCanvas, pur_file.yCanvas = unpack('>i', 216, 220), unpack('>i', 220, 224)

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
                pur_file.images.append(image_add)

                erase(4)
            else:
                image_add = PurImage()
                image_add.address = [start + read_pin, end + read_pin]
                image_add.pngBinary = pur_bytes[start: end]
                pur_file.images.append(image_add)

                erase(end)

        # Put duplicate images IDs in images too for later sorting
        # (duplicates = totalImageItems - images.count)
        # pngBinary here is not an actual PNG but the 4 byte ID of the transform that does have the PNG
        # after transforms are put in their images by address we can merge the duplicates
        for _ in range(total_image_items - len(pur_file.images)):
            image_add = PurImage()
            image_add.address = [read_pin, 4 + read_pin]
            image_add.pngBinary = pur_bytes[0: 4]
            pur_file.images.append(image_add)

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

        def add_text_children(parent: Item, number_of_children: int):
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
                pur_file.text.append(text)

            else:
                print("Error! Unknown item")  # Maybe more items will be added in the future
                break

    ################################################################################################################
    # Read the PureRef file
    ################################################################################################################

    read_header()  # Read header info, set total_image_items and PurFile.canvas

    read_images()  # Read all PNG image data, and duplicates (which are the transform.id from another image)

    read_items()  # Read all the items, and add them to the image_items list

    # After the final item, the header file_length is reached. This marks the beginning of the location and refs
    pur_file.folderLocation = unpack_string()

    # From now on the rest of the file is just a list coupling transform IDs (GraphicsImageItem)
    # with the address of the image (PurImage) it uses. Duplicate images are included and are removed later.
    for _ in range(total_image_items):  # Put transforms in their image
        red_id = unpack(">I", 0, 4)
        ref_address = [unpack(">Q", 4, 12), unpack(">Q", 12, 20)]
        for item in image_items:
            if red_id == item.id:
                for image in pur_file.images:
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
    for image in pur_file.images:  # Remove duplicate images and add their transform to the original image
        if is_duplicate(image):
            for other_image in pur_file.images:
                if struct.unpack('>I', image.pngBinary)[0] == other_image.transforms[0].id:
                    other_image.transforms += image.transforms
    # duplicates get removed, but links stay
    pur_file.images = [image for image in pur_file.images if not is_duplicate(image)]