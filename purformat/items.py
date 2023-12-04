from typing import List


# Abstract item class
class Item:
    def __init__(self):
        self.id = 0
        self.zLayer = 1.0
        self.matrix = \
            [1.0, 0.0,
             0.0, 1.0]
        self.x, self.y = 0.0, 0.0
        self.textChildren: List[PurGraphicsTextItem] = []  # both text and image items can have text children


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

    @property
    def width(self):
        return (self.points[0][2] - self.points[0][0]) * self.matrix[0]

    @width.setter
    def width(self, value):
        self.matrix[0] = value / (self.points[0][2] - self.points[0][0])

    @property
    def height(self):
        return (self.points[1][2] - self.points[1][0]) * self.matrix[3]

    @height.setter
    def height(self, value):
        self.matrix[3] = value / (self.points[1][2] - self.points[1][0])

    def scale(self, factor):
        self.matrix[0] *= factor
        self.matrix[3] *= factor

    def scale_to_width(self, width):
        ratio = self.height / self.width
        self.width = width
        self.height = width * ratio

    def scale_to_height(self, height):
        ratio = self.width / self.height
        self.width = height * ratio
        self.height = height

    def reset_crop(self, width, height):
        w = width/2
        h = height/2
        self.xCrop, self.yCrop = -float(w), -float(h)
        self.points = \
            [[-w, w, w, -w, -w],
             [-h, -h, h, h, -h]]


class PurImage:
    # Part of a PureRefObj
    # Holds an image and its transform(s) (usually only one)
    def __init__(self):
        self.address = [0, 0]  # original location for identification
        self.pngBinary = bytearray()  # image data
        self.transforms: List[PurGraphicsImageItem] = []  # transforms[] for multiple instances
