#!/usr/bin/env python3
"""
Trim the right side of the 3DS cartridge artwork to remove backing image.
This script:
1. Connects to the media.db database
2. Finds the Pokemon Alpha Sapphire 3DS game
3. Gets its disc_image (base64 PNG data URI)
4. Decodes and crops the image
5. Re-encodes and saves it back to the database
"""

import base64
import io
from pathlib import Path
from PIL import Image
from sqlalchemy import create_engine, text

# Database path
DATABASE_PATH = Path(__file__).parent / "backend" / "media.db"
print(f"Connecting to database: {DATABASE_PATH}")

# Create engine
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False, connect_args={"check_same_thread": False})

# Connect to database
connection = engine.connect()
transaction = connection.begin()

try:
    # Find the Pokemon Alpha Sapphire game
    result = connection.execute(text("""
        SELECT id, title, disc_image FROM mediaitem 
        WHERE title LIKE '%Pokemon%Alpha%Sapphire%' OR title = 'Pokémon Alpha Sapphire'
        LIMIT 1
    """)).fetchone()
    
    if not result:
        print("Game not found!")
        transaction.rollback()
        connection.close()
        exit(1)
    
    game_id, title, disc_image = result
    print(f"\nFound game: {title} (ID: {game_id})")
    
    if not disc_image:
        print("No disc_image found!")
        transaction.rollback()
        connection.close()
        exit(1)
    
    # Decode base64 image
    if disc_image.startswith("data:image/png;base64,"):
        base64_str = disc_image.split(",", 1)[1]
    else:
        base64_str = disc_image
    
    image_data = base64.b64decode(base64_str)
    img = Image.open(io.BytesIO(image_data))
    
    print(f"Original image size: {img.size} (width x height)")
    
    # Trim the right side by cropping
    # Remove approximately 10-15 pixels from the right side
    width, height = img.size
    trim_pixels = 12  # Adjust this value to trim more or less
    
    # Crop: (left, top, right, bottom)
    cropped_img = img.crop((0, 0, width - trim_pixels, height))
    
    print(f"Cropped image size: {cropped_img.size}")
    print(f"Trimmed {trim_pixels} pixels from the right side")
    
    # Re-encode to base64
    output = io.BytesIO()
    cropped_img.save(output, format="PNG")
    output.seek(0)
    new_base64 = base64.b64encode(output.getvalue()).decode()
    new_disc_image = f"data:image/png;base64,{new_base64}"
    
    print(f"New data URI length: {len(new_disc_image)} characters")
    
    # Update database
    connection.execute(text("""
        UPDATE mediaitem
        SET disc_image = :disc_image
        WHERE id = :id
    """), {"disc_image": new_disc_image, "id": game_id})
    
    transaction.commit()
    connection.close()
    print("\n✓ Database updated successfully!")
    print(f"  Game ID: {game_id}")
    print(f"  Game: {title}")
    print(f"  Image trimmed: {trim_pixels} pixels from right side")

except Exception as e:
    print(f"\n✗ Error: {e}")
    transaction.rollback()
    connection.close()
    exit(1)
