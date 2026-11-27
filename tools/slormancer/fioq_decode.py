import struct
import argparse
from PIL import Image

def color_hash_index(color):
    r, g, b, a = color
    return (r ^ g ^ b ^ a) % 64

def decode_diff_op(data: bytes, length: int, isSigned: bool, hasAlpha: bool, op_len=4) -> tuple:
    read_length = 4 if hasAlpha else 3
    
    total_bits = len(data) * 8
    required_bits_for_payload = length * read_length
    
    if total_bits < required_bits_for_payload + op_len:
        raise ValueError(
            f"Not enough data to read {read_length} values of {length} bits each, plus {op_len} for op code. "
            f"Total bits: {total_bits}, required for payload: {required_bits_for_payload}, op_len: {op_len}"
        )

    bit_str = ''.join(f'{byte:08b}' for byte in data)
    bit_str = bit_str[op_len:] # Discard the operand code bits from the start

    result = []
    for i in range(read_length):
        start = i * length
        end = start + length
        if end > len(bit_str):
             raise ValueError(
                f"Not enough bits left in bit_str for component {i}. Need {length} bits, have {len(bit_str)-start}. "
                f"Original data length: {len(data)}, op_len: {op_len}, current bit_str: '{bit_str}'"
             )
        bits = bit_str[start:end]

        value = int(bits, 2)
        if isSigned and bits[0] == '1': # Standard two's complement adjustment
            value -= (1 << length)
        result.append(value)
    
    return tuple(result)


DECODED_COUNT = 0


def decode_fioq(data, run_mask=0x0F):
    global DECODED_COUNT
    magic_bytes = data[:4]
    if magic_bytes != b'fioq':
        raise ValueError("Invalid FIOQ file: Missing 'fioq' magic bytes.")

    width = struct.unpack('<H', data[4:6])[0]
    height = struct.unpack('<H', data[6:8])[0]
    ops_payload_size = struct.unpack('<I', data[8:12])[0]
    
    if 12 + ops_payload_size > len(data):
        raise ValueError(f"Ops payload size ({ops_payload_size}) declared in header exceeds available data size ({len(data)-12}).")
    ops_payload = data[12:12 + ops_payload_size]

    op_offset = 0
    color_array = [[0, 0, 0, 0] for _ in range(64)] # Array of previously seen colors
    current_color = [0, 0, 0, 255] # Initial color (RGBA)
    pixel_pointer = 0
    pixels = []

    total_pixels = width * height
    if total_pixels == 0: # Handle zero-size images
        return Image.new("RGBA", (width, height))


    while pixel_pointer < total_pixels and op_offset < len(ops_payload):
        op = ops_payload[op_offset]

        # FIOQ_OP_INDEX: 00xxxxxx
        if op & 0xC0 == 0x00: 
            index = op & 0x3F
            current_color = color_array[index].copy()
            pixels.append(tuple(current_color))
            op_offset += 1
            pixel_pointer += 1
            continue

        # FIOQ_OP_RUN family: 01xxxxxx
        if op & 0xC0 == 0x40: 
            # FIOQ_OP_RUN_EX: 011xxxxx (extended run length)
            if op & 0xE0 == 0x60: 
                run_length = ((op & run_mask) << 8) + 33 # Selectable run-width variant
                op_offset += 1
                if op_offset >= len(ops_payload):
                     raise ValueError(f"FIOQ_OP_RUN_EX requires an extra byte for run_length, but payload ended.")
                run_length += ops_payload[op_offset]
                op_offset += 1
            # FIOQ_OP_RUN: 010xxxxx (short run length)
            else:
                run_length = (op & 0x3F) + 1 
                op_offset += 1

            for _ in range(run_length):
                if pixel_pointer >= total_pixels:
                     print(f"Warning: Run operation (length {run_length}) at pixel {pixel_pointer} would exceed total pixels ({total_pixels}). Truncating run.")
                     break
                pixels.append(tuple(current_color))
                pixel_pointer += 1
            continue

        # FIOQ_OP_DIFF_S (Small Diffs): 10xxxxxx
        if op & 0xC0 == 0x80: 
            # Data for decode_diff_op is the op byte itself. op_len=2 skips '10'.
            # Decodes 3x 2-bit signed diffs (dr, dg, db).
            diffs = decode_diff_op(bytes([op]), length=2, isSigned=True, hasAlpha=False, op_len=2)
            r_diff, g_diff, b_diff = diffs
            
            current_color[0] = (current_color[0] + r_diff) % 256
            current_color[1] = (current_color[1] + g_diff) % 256
            current_color[2] = (current_color[2] + b_diff) % 256
            
            pixels.append(tuple(current_color))
            color_array[color_hash_index(current_color)] = current_color.copy()
            pixel_pointer += 1
            op_offset += 1
            continue

        # FIOQ_OP_ADD_DIFF (1100xxxx, C-family) or FIOQ_OP_SUB_DIFF (1101xxxx, D-family)
        # Consumes 2 bytes: op-code, next_byte for G/B diffs. R-diff from op-code.
        if (op & 0xF0 == 0xC0) or (op & 0xF0 == 0xD0):
            op_code_byte = op # Save for r_diff calculation
            op_offset += 1 
            if op_offset >= len(ops_payload): 
                raise ValueError(f"FIOQ_OP_ADD/SUB_DIFF requires a second byte, but payload ended.")
            
            # Data for decode_diff_op is [op_code_byte, next_byte]. op_len=4 skips '1100'/'1101'.
            # decode_diff_op extracts 3 signed 4-bit diffs. R-diff component is then overridden.
            diff_payload_bytes = ops_payload[op_offset-1 : op_offset+1] 
            _, g_diff, b_diff = decode_diff_op(bytes(diff_payload_bytes), length=4, isSigned=True, hasAlpha=False, op_len=4)
            
            if op_code_byte & 0xF0 == 0xD0: # D-family (SUB_DIFF like)
                r_diff = (op_code_byte & 0x0F) - 16 # Results in -16 to -1
            else: # C-family (ADD_DIFF like)
                r_diff = (op_code_byte & 0x0F)       # Results in 0 to 15

            current_color[0] = (current_color[0] + r_diff) % 256
            current_color[1] = (current_color[1] + g_diff) % 256
            current_color[2] = (current_color[2] + b_diff) % 256
            
            pixels.append(tuple(current_color))
            color_array[color_hash_index(current_color)] = current_color.copy()
            pixel_pointer += 1
            op_offset += 1 # Consumed the next_byte
            continue

        # FIOQ_OP_DIFF_L (Large Diffs): 1110xxxx (E-family)
        # Consumes 3 bytes: op-code, data_byte1, data_byte2
        if op & 0xF0 == 0xE0: 
            if op_offset + 2 >= len(ops_payload): # Check if 2 more bytes exist
                raise ValueError(f"FIOQ_OP_DIFF_L requires two data bytes after op-code, but payload is too short.")
            
            # Data for decode_diff_op is [op_byte, byte1, byte2]. op_len=4 skips '1110'.
            # Extracts 4 signed 5-bit diffs (dr, dg, db, da).
            diff_payload_bytes = ops_payload[op_offset : op_offset+3] 
            r_diff, g_diff, b_diff, a_diff = decode_diff_op(bytes(diff_payload_bytes), length=5, isSigned=True, hasAlpha=True, op_len=4)

            current_color[0] = (current_color[0] + r_diff) % 256
            current_color[1] = (current_color[1] + g_diff) % 256
            current_color[2] = (current_color[2] + b_diff) % 256
            current_color[3] = (current_color[3] + a_diff) % 256
            
            pixels.append(tuple(current_color))
            color_array[color_hash_index(current_color)] = current_color.copy()
            pixel_pointer += 1
            op_offset += 3 # Consumed op-code + 2 data bytes
            continue

        # FIOQ_OP_CHANNEL: 1111xxxx (F-family)
        # Sets absolute channel values based on flags in xxxx (lower 4 bits of op-code)
        if op & 0xF0 == 0xF0:
            flags = op & 0x0F
            op_offset += 1 # Advance past op-code

            if flags & 0x08: # Red channel
                if op_offset >= len(ops_payload):
                     raise ValueError(f"FIOQ_OP_CHANNEL (R) requires a data byte, but payload ended.")
                current_color[0] = ops_payload[op_offset]
                op_offset += 1
            if flags & 0x04: # Green channel
                 if op_offset >= len(ops_payload):
                     raise ValueError(f"FIOQ_OP_CHANNEL (G) requires a data byte, but payload ended.")
                 current_color[1] = ops_payload[op_offset]
                 op_offset += 1
            if flags & 0x02: # Blue channel
                 if op_offset >= len(ops_payload):
                     raise ValueError(f"FIOQ_OP_CHANNEL (B) requires a data byte, but payload ended.")
                 current_color[2] = ops_payload[op_offset]
                 op_offset += 1
            if flags & 0x01: # Alpha channel
                 if op_offset >= len(ops_payload):
                     raise ValueError(f"FIOQ_OP_CHANNEL (A) requires a data byte, but payload ended.")
                 current_color[3] = ops_payload[op_offset]
                 op_offset += 1

            pixels.append(tuple(current_color))
            pixel_pointer += 1
            color_array[color_hash_index(current_color)] = current_color.copy()
            continue
        
        raise ValueError(f"Unknown FIOQ operation encountered at payload offset {op_offset} (file offset {op_offset+12}): OpCode {op:#04x} ({op:08b})")

    if pixel_pointer < total_pixels and op_offset >= len(ops_payload):
        print(f"Reached end of payload at offset {op_offset} but only {pixel_pointer}/{total_pixels} pixels decoded.")
    elif op_offset < len(ops_payload) and pixel_pointer >= total_pixels :
         print(f"Warning: Decoded all {total_pixels} pixels, but {len(ops_payload) - op_offset} bytes remain in ops payload (starting at offset {op_offset}).")

    if len(pixels) != total_pixels:
        print(f"Decoded pixel count ({len(pixels)}) does not match expected image size ({total_pixels}). Output image may be incomplete or corrupt.")
    
    img = Image.new("RGBA", (width, height))
    
    img.putdata(pixels[:total_pixels]) 

    DECODED_COUNT = len(pixels)
    return img

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decode FIOQ image files.")
    parser.add_argument("input")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    if not args.output:
        args.output = args.input + ".png"

    with open(args.input, "rb") as f:
        data = f.read()
    img = decode_fioq(data) 
    img.save(args.output)
    print(f"Decoding complete. Image saved as {args.output}")