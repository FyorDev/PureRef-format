# Abstract item class
class Item:
    def __init__(self):
        self.id = 0
        self.zLayer = 1.0
        self.matrix = \
            [1.0, 0.0,
             0.0, 1.0]
        self.x, self.y = 0.0, 0.0
        self.textChildren = []  # both text and image items can have text children


# Similar to image transform, but this carries its own content (text)
class PurGraphicsTextItem(Item):
    # Part of a PureRefObj

    def __init__(self):
        super().__init__()
        self.text = ""
        self.opacity = 65535
        self.rgb = \
            [65535,
             65535,
             65535]
        self.opacityBackground = 5000
        self.rgbBackground = [0, 0, 0]


class PurGraphicsImageItem(Item):
    # Part of a PurImage
    # Be aware: PureRef transforms have an alternative second format for
    # rotated cropping where the image is no longer a rectangle

    def __init__(self):
        super().__init__()
        self.source = "BruteForceLoaded"
        self.name = "image"
        self.matrixBeforeCrop = \
            [1.0, 0.0,
             0.0, 1.0]
        self.xCrop, self.yCrop = 0.0, 0.0
        self.scaleCrop = 1.0
        self.pointCount = 5  # 4 byte
        self.points = \
            [[-1000, 1000, 1000, -1000, -1000],
             [-1000, -1000, 1000, 1000, -1000]]  # 4 byte 01 and 2 doubles

    def reset_crop(self, width, height):
        self.xCrop, self.yCrop = -float(width/2), -float(height/2)
        w = width/2
        h = height/2
        self.points = \
            [[-w, w, w, -w, -w],
             [-h, -h, h, h, -h]]


class PurImage:
    # Part of a PureRefObj
    # Holds an image and its transform(s) (usually only one)
    def __init__(self):
        self.address = [0, 0]  # original location for identification
        self.pngBinary = bytearray()  # image data
        self.transforms = []  # transforms[] for multiple instances
