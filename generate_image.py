from PIL import Image

def generate_image(width, height, color):
    img = Image.new('RGB', (width, height), color = color)
    img.save('generated_image.png')

generate_image(100, 100, (73, 109, 137))