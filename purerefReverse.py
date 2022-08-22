import os
import struct
import colorsys

class PurGraphicsTextItem:
    # Part of a PureRefObj

    # ASCII text contents
    text = ""
    matrix = [1.0, 0.0, 0.0, 1.0]
    x, y = 0.0, 0.0
    zLayer = 1.0
    id = 0
    opacity = 65535
    rgb = [65535, 65535, 65535]
    opacityBackground = 5000
    rgbBackground = [0, 0, 0]

    def __init__(self):
        self.matrix = [1.0, 0.0, 0.0, 1.0]     
        self.rgb = [65535, 65535, 65535]
        self.rgbBackground = [0, 0, 0]
   
    # own simple text transform

class PurGraphicsImageItem:
        
    # Part of a PurImage
    # Be aware: PureRef transforms have an alternative second format for rotated cropping where the image is no longer a rectangle
    source = ("BruteForceLoaded".encode("utf-16-le")[31:32] + "BruteForceLoaded".encode("utf-16-le")[0:31]).decode("utf-8")
    name = ("image".encode("utf-16-le")[9:10] + "image".encode("utf-16-le")[0:9]).decode("utf-8")
    matrix = [1.0, 0.0, 0.0, 1.0]
    x, y = 0.0, 0.0
    id = 0
    zLayer = 1.0

    matrixBeforeCrop = [1.0, 0.0, 0.0, 1.0]
    xCrop, yCrop  = 0.0, 0.0
    scaleCrop = 1.0
    pointCount = 5 #4 byte
    points = [[-1000, 1000, 1000, -1000, -1000],[-1000, -1000, 1000, 1000, -1000]] # 4 byte 01 and 2 doubles
    def __init__(self):
        self.matrix = [1.0, 0.0, 0.0, 1.0]
        self.matrixBeforeCrop = [1.0, 0.0, 0.0, 1.0]
        self.points = [[-1000, 1000, 1000, -1000, -1000],[-1000, -1000, 1000, 1000, -1000]]
    
    def resetCrop(self, width, height):
        self.xCrop, self.yCrop  = -float(width/2), -float(height/2)
        width = width/2
        height = height/2
        self.points = [[-width, width, width, -width, -width],[-height, -height, height, height, -height]]

    def setSource(self, source):
        self.source = (source.encode("utf-16-le")[len(source)*2-1:len(source)*2] + source.encode("utf-16-le")[0:len(source)*2-1]).decode("utf-8")

    def setName(self, name):
        self.name = (name.encode("utf-16-le")[len(name)*2-1:len(name)*2] + name.encode("utf-16-le")[0:len(name)*2-1]).decode("utf-8")



class PurImage:
    # Part of a PureRefObj
    # Holds an image and its transform(s) 

    # original location for identification
    address = [0,0]

    # image data
    pngBinary:bytearray = []

    # transforms[] for multiple instances
    transforms = []

    def __init__(self):
        self.address = [0,0]
        self.pngBinary:bytearray = []
        self.transforms = []




###################
#
# The class this whole project is about
#
# Build an interpreter for this class to make your own PureRef converter to/from any file without having to decipher the hex bytes like I had to
#
###################

class PurerefObject:
    # A class holding all the images (which include their own transforms), text and anything else that would be in a .pur file
    # Can be exported to a .pur file, can be imported from a .pur file and can be generated from images to later export

    # Canvas width and height
    canvas = [-10000.0, -10000.0, 10000.0, 10000.0]
    # View zoom level
    zoom = 1.0
    # View location
    xCanvas, yCanvas = 0, 0

    folderLocation = os.getcwd()

    # image list
    images = []

    # text list
    text = []



    def CountImageItems(self):
        # Count the amount of image transforms and assign their IDs
        count = 0
        for image in self.images:
            for transform in image.transforms:
                transform.id = count
                count += 1
        return count

    # Import a .pur file into this object
    def read(self, file:str):
        purBytes = bytearray(open(file, "rb").read())
        # ReadPin to remember addresses while removing bytes
        readPin = 0

        totalTextItems = struct.unpack('>H', purBytes[12:14] )[0] - struct.unpack('>H', purBytes[14:16] )[0]
        totalImageItems = struct.unpack('>H', purBytes[14:16] )[0]
        fileLength = struct.unpack('>Q', purBytes[16:24] )[0]

        # Canvas width and height
        self.canvas = [
            struct.unpack('>d', purBytes[112:120] )[0],
            struct.unpack('>d', purBytes[120:128] )[0],
            struct.unpack('>d', purBytes[128:136] )[0],
            struct.unpack('>d', purBytes[136:144] )[0],
        ]
        self.zoom = struct.unpack('>d', purBytes[144:152] )[0]
        self.xCanvas, self.yCanvas = struct.unpack('>i', purBytes[216:220] )[0], struct.unpack('>i', purBytes[220:224] )[0]

        #
        # Done reading header, remove and update readPin
        #
        purBytes[0:224] = []
        readPin = 224

        # Read all images, no transforms yet
        while purBytes.__contains__(bytearray([137, 80, 78, 71,   13, 10, 26, 10])):
            start = purBytes.find( bytearray([137, 80, 78, 71,   13, 10, 26, 10]))
            end = purBytes.find ( bytearray([0, 0, 0, 0,   73, 69, 78, 68,   174, 66, 96, 130])) + 12

            if start >= 4:
                image = PurImage()
                image.address = [readPin, 4+readPin]
                image.pngBinary = purBytes[0: 4]
                self.images.append(image)

                purBytes[0: 4] = []
                readPin += 4
            else:
                image = PurImage()
                image.address = [start+readPin, end+readPin]
                image.pngBinary = purBytes[start: end]
                self.images.append(image)

                purBytes[start: end] = []
                readPin += end-start
        
        # Put duplicate images IDs in images too for later sorting
        # (duplicates = totalImageItems - images.count)
        # pngBinary here is not an actual PNG but the 4 byte ID of the transform that does have the PNG
        # after transforms are put in their images by address we can merge the duplicate transforms into the real images
        for i in range(totalImageItems - len(self.images)):
            image = PurImage()
            image.address = [readPin, 4+readPin]
            image.pngBinary = purBytes[0: 4]
            self.images.append(image)

            purBytes[0: 4] = []
            readPin += 4


        ImageItems = []
        ###
        #
        # Read all GraphicsImageItems and GraphicsTextItems, they are in the order they were added
        #
        ###
        while(struct.unpack(">I", purBytes[8:12])[0] == 34 or struct.unpack(">I", purBytes[8:12])[0] == 32):
            if struct.unpack(">I", purBytes[8:12])[0] == 34:
                transformEnd = struct.unpack(">Q", purBytes[0:8])[0]
                transform = PurGraphicsImageItem()
                if struct.unpack(">I", purBytes[8:12])[0] != 34:
                    print("Read Error! expected GraphicsImageItem")

                # Remove imageItem standard text
                readPin += 12 + struct.unpack(">I", purBytes[8:12])[0]
                purBytes[0:12 + struct.unpack(">I", purBytes[8:12])[0] ] = []

                # Check if bruteforceloaded
                BruteForceLoaded = False
                if struct.unpack(">I", purBytes[0:4])[0] == 0:
                    BruteForceLoaded = True
                    purBytes[0:4] = []
                    readPin += 4
                    print("BruteForceLoad")

                # Read&Remove source
                if struct.unpack(">i", purBytes[0:4])[0] == -1:
                        readPin += 4
                        purBytes[0:4] = []                        
                else:
                    transform.source = purBytes[4:4+ struct.unpack(">I", purBytes[0:4])[0] ].decode("utf-8", errors="replace")
                    readPin += 4 + struct.unpack(">I", purBytes[0:4])[0]
                    purBytes[0:4+ struct.unpack(">I", purBytes[0:4])[0] ] = []

                # Read&Remove name
                if not BruteForceLoaded:
                    if struct.unpack(">i", purBytes[0:4])[0] == -1:
                        readPin += 4
                        purBytes[0:4] = []
                    else:
                        transform.name = purBytes[4:4+ struct.unpack(">I", purBytes[0:4])[0] ].decode("utf-8", errors="replace")
                        readPin += 4 + struct.unpack(">I", purBytes[0:4])[0]
                        purBytes[0:4+ struct.unpack(">I", purBytes[0:4])[0] ] = []

                # Unknown permanent 1.0 float we don't want
                if struct.unpack('>d', purBytes[0:8] )[0] != 1.0:
                    print("Notice: mysterious permanent float is not 1.0 (investigate?) ", struct.unpack('>d', purBytes[0:8] )[0])
                purBytes[0:8] = []
                readPin += 8

                # Time for matrix for scaling & rotation
                transform.matrix[0] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                transform.matrix[1] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16                        
                transform.matrix[2] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                transform.matrix[3] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16    

                # Location
                transform.x = struct.unpack('>d', purBytes[0:8] )[0]
                purBytes[0:8] = []
                readPin += 8           
                transform.y = struct.unpack('>d', purBytes[0:8] )[0]
                purBytes[0:8] = []
                readPin += 8

                # Second unknown permanent 1.0 float we don't want
                if struct.unpack('>d', purBytes[0:8] )[0] != 1.0:
                    print("Notice: mysterious permanent float2 is not 1.0 (investigate?) ", struct.unpack('>d', purBytes[0:8] )[0])
                purBytes[0:8] = []
                readPin += 8

                # ID and Zlayer
                transform.id = struct.unpack(">I", purBytes[0:4])[0]
                transform.zLayer = struct.unpack(">d", purBytes[4:12])[0]
                purBytes[0:12] = []
                readPin += 12

                # Time for matrixBeforeCrop for scaling & rotation
                transform.matrixBeforeCrop[0] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                transform.matrixBeforeCrop[1] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16                        
                transform.matrixBeforeCrop[2] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                transform.matrixBeforeCrop[3] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16    

                # Location before crop
                transform.xCrop = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8           
                transform.yCrop = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8

                # Finally crop scale
                transform.scaleCrop = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8

                #
                # Points of crop
                #
                # Why are there n+1? No idea but the first seems to be a copy of the last, maybe it's offset
                #
                pointCount = struct.unpack(">I", purBytes[0:4])[0]
                purBytes[0:4] = []
                readPin += 4

                pointsReplace = [[],[]]
                for i in range(pointCount):
                    pointsReplace[0].append(struct.unpack('>d', purBytes[4:12])[0])
                    pointsReplace[1].append(struct.unpack('>d', purBytes[12:20])[0])     
                    purBytes[0:20] = []
                    readPin += 20
                transform.points = pointsReplace

                purBytes[0:transformEnd - readPin] = []
                readPin += transformEnd - readPin

                ImageItems.append(transform)

            #
            # Text item
            #
            elif struct.unpack(">I", purBytes[8:12])[0] == 32:
                textEnd = struct.unpack(">Q", purBytes[0:8])[0]

                textTransform = PurGraphicsTextItem()
                if struct.unpack(">I", purBytes[8:12])[0] != 32:
                    print("Read Error! expected GraphicsTextItem")

                # Remove textItem standard text
                readPin += 12 + struct.unpack(">I", purBytes[8:12])[0]
                purBytes[0:12 + struct.unpack(">I", purBytes[8:12])[0] ] = []

                # Read the text
                textTransform.text = purBytes[4:4+ struct.unpack(">I", purBytes[0:4])[0] ].decode("utf-8", errors="replace")
                readPin += 4 + struct.unpack(">I", purBytes[0:4])[0]
                purBytes[0:4 + struct.unpack(">I", purBytes[0:4])[0]] = []

                # Time for matrix for scaling & rotation
                textTransform.matrix[0] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                textTransform.matrix[1] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16                        
                textTransform.matrix[2] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                textTransform.matrix[3] = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:16] = []
                readPin += 16   

                # Location
                textTransform.x = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8
                textTransform.y = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8

                # text unknown permanent 1.0 float we don't want
                if struct.unpack('>d', purBytes[0:8] )[0] != 1.0:
                    print("Notice: mysterious text permanent float is not 1.0 (investigate?) ", struct.unpack('>d', purBytes[0:8] )[0])
                purBytes[0:8] = []
                readPin += 8

                # These have an id too
                textTransform.id = struct.unpack('>I', purBytes[0:4])[0]
                purBytes[0:4] = []
                readPin += 4
            
                # Z layer
                textTransform.zLayer = struct.unpack('>d', purBytes[0:8])[0]
                purBytes[0:8] = []
                readPin += 8    

                # byte indicating RGB or HSV
                IsHSV = struct.unpack('>b', purBytes[0:1])[0] == 2
                purBytes[0:1] = []
                readPin += 1

                # Opacity
                textTransform.opacity = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2
                # RGB
                textTransform.rgb[0] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2          
                textTransform.rgb[1] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2    
                textTransform.rgb[2] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2

                if IsHSV:
                    textTransform.rgb = list(colorsys.hsv_to_rgb((textTransform.rgb[0]) /35900, (textTransform.rgb[1]) /65535, (textTransform.rgb[2]) /65535 ))
                    textTransform.rgb[0] = int(textTransform.rgb[0] * 65535)
                    textTransform.rgb[1] = int(textTransform.rgb[1] * 65535)
                    textTransform.rgb[2] = int(textTransform.rgb[2] * 65535)
                # Unknown 2 bytes and is hsv byte
                IsBackgroundHSV = struct.unpack('>b', purBytes[2:3])[0] == 2
                purBytes[0:3] = []
                readPin += 3

                # BackgroundOpacity
                textTransform.opacityBackground = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2
                # BackgroundRGB
                textTransform.rgbBackground[0] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2          
                textTransform.rgbBackground[1] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2    
                textTransform.rgbBackground[2] = struct.unpack('>H', purBytes[0:2])[0]
                purBytes[0:2] = []
                readPin += 2

                if IsBackgroundHSV:
                    textTransform.rgbBackground = list(colorsys.hsv_to_rgb((textTransform.rgbBackground[0]) /35900, (textTransform.rgbBackground[1]) /65535, (textTransform.rgbBackground[2]) /65535 ))
                    textTransform.rgbBackground[0] = int(textTransform.rgbBackground[0] * 65535)
                    textTransform.rgbBackground[1] = int(textTransform.rgbBackground[1] * 65535)
                    textTransform.rgbBackground[2] = int(textTransform.rgbBackground[2] * 65535)
                self.text.append(textTransform)
                purBytes[0:textEnd - readPin] = []
                readPin += textEnd - readPin
            else:
                print("Error! Unknown item")
                break
        

        #
        #   All items done!
        #   ImageItems are in ImageItems[] to link with images later
        #

        self.folderLocation = purBytes[4:4+struct.unpack('>I', purBytes[0:4])[0]].decode("utf-8")
        readPin += 4+struct.unpack('>I', purBytes[0:4])[0]     
        purBytes[0:4+struct.unpack('>I', purBytes[0:4])[0]] = []
        
        # Put transforms in images (including empty reference images)
        for i in range(totalImageItems):
            refid = struct.unpack('>I', purBytes[0:4])[0]
            refaddress = [struct.unpack('>Q', purBytes[4:12])[0], struct.unpack('>Q', purBytes[12:20])[0]]
            for item in ImageItems:
                if refid == item.id:
                    for image in self.images:
                        if refaddress[0] == image.address[0]:
                            image.transforms = [item]

            purBytes[0:20] = []
            readPin += 20

        # Put all duplicate images together
        for image in self.images:
            if len(image.pngBinary) == 4:
                for otherimage in self.images:
                    if struct.unpack('>I', image.pngBinary)[0] == otherimage.transforms[0].id:
                        otherimage.transforms += image.transforms
        self.images = [image for image in self.images if len(image.pngBinary) != 4]



    # Export this object to a .pur file
    def write(self, file:str):
        # A standard empty header for PureRef 1.11
        purBytes = bytearray(b'\x00\x00\x00\x08\x001\x00.\x001\x000\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01&\x00\x00\x00\x0c\x001\x00.\x001\x001\x00.\x001\x00\x00\x00@\x005\x00b\x00e\x00b\x00c\x002\x00c\x00f\x00f\x003\x001\x005\x001\x00b\x001\x00c\x000\x007\x000\x004\x009\x00d\x003\x00e\x00e\x00a\x00e\x000\x006\x005\x005\x00f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00?\xf0\x00\x00\x00\x00\x00\x00?\xf0\x00\x00\x00\x00\x00\x00?\xf0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00?\xf0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00?\xf0\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        # Write GraphicsImageItem+GraphicsTextItem count and GraphicsImageItem count
        imageitems = self.CountImageItems()
        purBytes[12:14] = bytearray( struct.pack(">H", imageitems + len(self.text)))
        purBytes[14:16] = bytearray( struct.pack(">H", imageitems ))

        # Write (and assign) GraphicsImageItem ID count, not usually the same but we discard unused transform IDs
        purBytes[108:114] = bytearray( struct.pack(">I", imageitems + len(self.text)))
        # ImageItems received IDs in CountImageItems(), now give text their own ID
        for i in range(len(self.text)):
            self.text[i].id = imageitems + i

        # Write canvas width and height
        purBytes[112:144] = (
            bytearray(struct.pack(">d", self.canvas[0])) + 
            bytearray(struct.pack(">d", self.canvas[1])) + 
            bytearray(struct.pack(">d", self.canvas[2])) + 
            bytearray(struct.pack(">d", self.canvas[3]))
        )
        # Write canvas view zoom, you want x and y zoom to be the same
        purBytes[144:152] = bytearray(struct.pack(">d", self.zoom))
        purBytes[176:184] = bytearray(struct.pack(">d", self.zoom))
        # Write canvas view X and Y
        purBytes[216:224] = bytearray(struct.pack(">i", self.xCanvas)) + bytearray(struct.pack(">i", self.yCanvas))

        # Add all images
        for image in self.images:
            image.address[0] = len(purBytes)
            purBytes += image.pngBinary
            image.address[1] = len(purBytes)
        
        references = []
        #
        # Create references including duplicates
        # 
        for image in self.images:
            i=0
            parent = object
            for transform in image.transforms:
                if i == 0:
                    parent = transform
                    references.append([transform.id, image.address[0], image.address[1]])
                else:
                    references.append([transform.id, len(purBytes), len(purBytes)+4])
                    purBytes += bytearray(struct.pack(">i", parent.id))

                i+=1

        if(len(self.images) > 0):
            # Sort all imagetransforms and references by the order in which they appear in memory
            transformsOrdered = []
            for image in self.images:
                for transform in image.transforms:
                    transformsOrdered.append(transform)
            # Sort images transforms by addresses too
            referencesZip = zip(references, transformsOrdered)
            referencesZip = sorted(referencesZip, key=lambda x: x[0][1])
            references, transformsOrdered = map(list, zip(*referencesZip))

        #
        # Add transforms
        #
        
            for transform in transformsOrdered:      
                # transformEnd prints current writePin for now to replace later 
                transformEnd = len(purBytes)
                purBytes += bytearray(struct.pack(">Q", 0))
                # Purimageitem text
                BruteForceLoaded = transform.source.encode("utf-8") == "BruteForceLoaded".encode("utf-16-le")[31:32] + "BruteForceLoaded".encode("utf-16-le")[0:31]
                purBytes += struct.pack(">I", 34)
                purBytes += struct.pack(">b", 0)
                purBytes += "GraphicsImageItem".encode("utf-16-le")
                # Is bruteforceloaded there is an extra empty 8 byte
                if BruteForceLoaded:
                    purBytes += struct.pack(">I", 0)
                # Source
                purBytes[len(purBytes)-1:len(purBytes)] = struct.pack(">I", len(transform.source.encode("utf-8")))
                purBytes += transform.source.encode("utf-8")
                # Name (skipped if bruteforceloaded)
                # PureRef can have empty names but we have BruteForceLoaded as default
                if not BruteForceLoaded:
                    purBytes += struct.pack(">I", len(transform.name.encode("utf-8")))
                    purBytes += transform.name.encode("utf-8")
                
                #
                # Start actual transform
                #
                
                # Mysterious 1.0 double
                purBytes += struct.pack(">d", 1.0)
                # Scaling matrix
                purBytes += struct.pack(">d", transform.matrix[0])
                purBytes += struct.pack(">d", transform.matrix[1])
                purBytes += struct.pack(">d", 0.0)
                purBytes += struct.pack(">d", transform.matrix[2])
                purBytes += struct.pack(">d", transform.matrix[3])
                purBytes += struct.pack(">d", 0.0)
                # Location
                purBytes += struct.pack(">d", transform.x)
                purBytes += struct.pack(">d", transform.y)
                # Mysterious 1.0 double
                purBytes += struct.pack(">d", 1.0)
                # ID and ZLayer
                purBytes += struct.pack(">I", transform.id)
                purBytes += struct.pack(">d", transform.zLayer)
                # MatrixBeforeCrop
                purBytes += struct.pack(">d", transform.matrixBeforeCrop[0])
                purBytes += struct.pack(">d", transform.matrixBeforeCrop[1])
                purBytes += struct.pack(">d", 0.0)
                purBytes += struct.pack(">d", transform.matrixBeforeCrop[2])
                purBytes += struct.pack(">d", transform.matrixBeforeCrop[3])
                purBytes += struct.pack(">d", 0.0)
                # Location before crop
                purBytes += struct.pack(">d", transform.xCrop)
                purBytes += struct.pack(">d", transform.yCrop)
                # Finally crop scale
                purBytes += struct.pack(">d", transform.scaleCrop)

                # Number of crop points
                purBytes += struct.pack(">I", len(transform.points[0]))
                for i in range(len(transform.points[0])):
                    if i == 0:
                        purBytes += struct.pack(">I", 0)
                    else:
                        purBytes += struct.pack(">I", 1)
                    purBytes += struct.pack(">d", transform.points[0][i])
                    purBytes += struct.pack(">d", transform.points[1][i])                    

                # No idea if this actually holds information but it always looks the same
                purBytes += struct.pack(">d", 0.0)
                purBytes += struct.pack(">I", 1)
                purBytes += struct.pack(">b", 0)       
                purBytes += struct.pack(">q", -1)       
                purBytes += struct.pack(">I", 0)



                # Start of transform needs its own end address
                purBytes[transformEnd:transformEnd+8] = bytearray(struct.pack(">Q", len(purBytes)))

        #
        #   DONE image transforms loaded
        #

        # Time for text
        for textTransform in self.text:
            transformEnd = len(purBytes)
            purBytes += bytearray(struct.pack(">Q", 0))

            purBytes[transformEnd:transformEnd+8] = bytearray(struct.pack(">Q", len(purBytes)))
            purBytes += struct.pack(">I", 32)
            purBytes += struct.pack(">b", 0)
            purBytes += "GraphicsTextItem".encode("utf-16-le")
            purBytes[len(purBytes)-1:len(purBytes)] = []
            # The text
            purBytes += struct.pack(">I", len(textTransform.text))
            purBytes += textTransform.text.encode("utf-8")

            # Matrix
            purBytes += struct.pack(">d", textTransform.matrix[0])
            purBytes += struct.pack(">d", textTransform.matrix[1])
            purBytes += struct.pack(">d", 0.0)
            purBytes += struct.pack(">d", textTransform.matrix[2])
            purBytes += struct.pack(">d", textTransform.matrix[3])
            purBytes += struct.pack(">d", 0.0)

            # Location
            purBytes += struct.pack(">d", textTransform.x)    
            purBytes += struct.pack(">d", textTransform.y)   
            # Mysterious 1.0 float
            purBytes += struct.pack(">d", 1.0)
            # ID
            purBytes += struct.pack(">I", textTransform.id)
            # Zlayer
            purBytes += struct.pack(">d", textTransform.zLayer)
            # Weird meaningless byte
            purBytes += struct.pack(">b", 1)
            # Opacity n RGB
            purBytes += struct.pack(">H", textTransform.opacity)
            purBytes += struct.pack(">H", textTransform.rgb[0])
            purBytes += struct.pack(">H", textTransform.rgb[1])
            purBytes += struct.pack(">H", textTransform.rgb[2])
            # Mysterious thing that counts something about background
            purBytes += struct.pack(">H", 0)
            purBytes += struct.pack(">b", 1)
            # Background opacity n RGB
            purBytes += struct.pack(">H", textTransform.opacityBackground)
            purBytes += struct.pack(">H", textTransform.rgbBackground[0])
            purBytes += struct.pack(">H", textTransform.rgbBackground[1])
            purBytes += struct.pack(">H", textTransform.rgbBackground[2])
            purBytes += struct.pack(">I", 0)
            purBytes += struct.pack(">H", 0)

            # Start of transform needs its own end address
            purBytes[transformEnd:transformEnd+8] = bytearray(struct.pack(">Q", len(purBytes)))


        # Location
        purBytes += struct.pack(">I", len(self.folderLocation))    
        purBytes += self.folderLocation.encode("utf-8")
        purBytes[16:24] = bytearray(struct.pack(">Q", len(purBytes)))


        for reference in references:
            purBytes += struct.pack(">I", reference[0])
            purBytes += struct.pack(">Q", reference[1])
            purBytes += struct.pack(">Q", reference[2])



        with open(file, "wb") as f:
            f.write(purBytes)

