import purformat.items as items
from purformat import purformat
from PIL import Image
import os
import re
from io import BytesIO

####################################################################################################
# This function will create a neatly organized .pur (PureRef) file from a folder with PNG or JPG images
# It is used in pureref_gen_script.py to create .pur files from all folders in Artists/
####################################################################################################


def generate(read_folder, write_file):

    # Natural sort https://stackoverflow.com/a/341745
    # For example: 0.jpg, 2.jpg, 10.jpg, 100.jpg
    # Instead of: 0.jpg, 10.jpg, 100.jpg, 2.jpg
    def natural_keys(text):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]

    def process_image(path):
        if not (path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".png")):
            print("Skipping processing, not a valid image: " + path)
            return None

        print("Processing: " + path)

        image = Image.open(path).convert(mode="RGB")
        pur_image = items.PurImage()

        with BytesIO() as f:
            image.save(f, format="PNG", compress_level=7)  # TODO: research why PureRef saves PNG differently sometimes
            pur_image.pngBinary = f.getvalue()
            # bytes are used instead of PIL because the pngBinary can also be a reference to another image's transform
            # (duplicate images) this is the easiest way to handle it TODO: make PurFile work with PIL images

        pur_transform = items.PurGraphicsImageItem()
        pur_transform.reset_crop(image.width, image.height)
        pur_transform.name = path.replace(".jpg", "")
        pur_transform.source = path
        pur_image.transforms = [pur_transform]  # the first transform is the original, rest are duplicates

        return pur_image

    # Initialize an empty .pur file which will hold objects for images with transforms(1, n), and text
    pur_file = purformat.PurFile()

    # Add all images in read_folder to pur_file
    # The images will be sorted using natural sort, number them to control order
    files = sorted(os.listdir(read_folder), key=natural_keys)
    pur_file.images = [process_image(os.path.join(read_folder, file)) for file in files]
    pur_file.images = [image for image in pur_file.images if image is not None]  # remove None values

    if not pur_file.images:
        print("Skipping, no valid images found in " + read_folder)
        return

    # Start transforming images to automatically order
    transforms = [transform for image in pur_file.images for transform in image.transforms]

    for transform in transforms:  # normalize all images to height 1000
        transform.matrix = [1000/(2*transform.points[1][2]), 0.0, 0.0, 1000/(2*transform.points[1][2])]  # TODO: extract to items.py

    total_width = sum([transform.matrix[0]*2*transform.points[0][2] for transform in transforms])  # TODO: extract to items.py

    # Divide into rows by cutting in half until it is rectangular enough
    rows = [transforms]  # Initially one row, list of rows with so far only one list of transforms.
    # TODO: alternative rectangle algorithm, extract to function with ratio arguments
    while len(rows)*2000.0 < total_width:  # while more wide than tall, eventually making a decent rectangle
        total_width /= 2.0
        new_rows = []

        for row in rows:
            row_length = total_width

            # get the index of the middle transform by summing widths until it exceeds half of the total width
            middle_index = 0
            while row_length > 0:
                row_length -= row[middle_index].matrix[0]*row[middle_index].points[0][2]*2  # TODO: extract to items.py
                middle_index += 1

            # split the row in half
            new_rows.append(row[:middle_index])
            new_rows.append(row[middle_index:])

        rows = new_rows

    # Normalize row widths and actually place images, this makes everything line up perfectly.
    transform_y_old = 0
    transform_y = 0
    for row in rows:
        row_width = 1  # 1 to avoid division by zero
        for transform in row:
            row_width += transform.matrix[0]*transform.points[0][2]*2
        for transform in row:
            transform.matrix[0] *= 20000/row_width
            transform.matrix[3] *= 20000/row_width
        transform_y += 1000 * 20000/row_width
        row_width = 1  # 1 to avoid division by zero
        for transform in row:
            transform.x = row_width + transform.matrix[0]*transform.points[0][2]
            row_width += transform.matrix[0]*transform.points[0][2]*2
            transform.y = transform_y_old + transform.matrix[0]*transform.points[1][2]
        transform_y_old = transform_y

    pur_file.write(write_file)
    print("Done! File created")
