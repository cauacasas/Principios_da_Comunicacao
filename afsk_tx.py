import numpy as np
from scipy.io.wavfile import write as wav_write
from afsk_utils import (
    FS, SAMPLES_PER_BIT, PREAMBLE_BYTE, SYNC_WORD,
    ascii_to_bits, modulate_bit, calculate_crc16_ccitt
)

# --- Constantes de Framing ---
# Preamble: 4 bytes (0xAA repetido)
PREAMBLE_BYTES = bytes([PREAMBLE_BYTE] * 4)
# Sync Word: 2 bytes (0x2DD4)
SYNC_WORD_BYTES = SYNC_WORD.to_bytes(2, byteorder='big')
# Tamanho fixo dos campos de cabeçalho (sem payload e CRC)
HEADER_FIXED_SIZE = len(PREAMBLE_BYTES) + len(SYNC_WORD_BYTES) + 1 + 1 + 1 # Preamble + Sync + ID_TX + ID_RX + Len

def build_packet(message: str, user_id_tx: int, user_id_rx: int = 0) -> bytes:
    """
    Constrói o pacote de dados completo (formato estendido) a partir da mensagem de texto.
    
    Estrutura do Pacote (Bytes):
    [Preamble (4)] [Sync_Word (2)] [User_ID TX (1)] [User_ID RX (1)] [Len (1)] [Payload (0-255)] [CRC-16 (2)]
    
    Args:
        message (str): A mensagem de texto a ser transmitida (Payload).
        user_id_tx (int): ID do transmissor (0-255).
        user_id_rx (int): ID do receptor (0-255).
        
    Returns:
        bytes: O pacote de dados completo (incluindo CRC).
    """
    
    # 1. Payload (Mensagem)
    payload_bytes = message.encode('ascii')
    payload_len = len(payload_bytes)
    
    if payload_len > 255:
        raise ValueError("Mensagem muito longa. O Payload deve ter no máximo 255 bytes.")
        
    # 2. Campos de Cabeçalho (excluindo Preamble e Sync_Word para o CRC)
    # [User_ID TX (1)] [User_ID RX (1)] [Len (1)] [Payload (0-255)]
    header_data = bytes([user_id_tx, user_id_rx, payload_len])
    data_for_crc = header_data + payload_bytes
    
    # 3. Cálculo do CRC-16-CCITT
    crc_bytes = calculate_crc16_ccitt(data_for_crc)
    
    # 4. Montagem do Pacote Completo
    # [Preamble (4)] [Sync_Word (2)] [User_ID TX (1)] [User_ID RX (1)] [Len (1)] [Payload (0-255)] [CRC-16 (2)]
    full_packet = (
        PREAMBLE_BYTES + 
        SYNC_WORD_BYTES + 
        data_for_crc + 
        crc_bytes
    )
    
    return full_packet

def packet_to_bits(packet_bytes: bytes) -> list[int]:
    """
    Converte o pacote de bytes em uma sequência de bits (NRZ, MSB-first).
    """
    bits = []
    for byte in packet_bytes:
        # Converte cada byte em 8 bits (MSB-first)
        bits.extend([int(b) for b in format(byte, '08b')])
    return bits

def modulate_packet(packet_bytes: bytes) -> np.ndarray:
    """
    Converte o pacote de bytes em um sinal de áudio AFSK.
    """
    # 1. Converte o pacote em bits
    bit_sequence = packet_to_bits(packet_bytes)
    
    # 2. Modula cada bit
    audio_samples = []
    for bit in bit_sequence:
        audio_samples.append(modulate_bit(bit))
        
    # 3. Concatena todas as amostras
    # O resultado é um array de ponto flutuante (float64)
    return np.concatenate(audio_samples)

def save_afsk_signal(signal: np.ndarray, filename: str):
    """
    Salva o sinal de áudio AFSK em um arquivo WAV (8 kHz, 16 bits PCM).
    """
    # Converte o sinal de float (-1.0 a 1.0) para int16 (-32768 a 32767)
    # O sinal foi normalizado em afsk_utils para amplitude máxima de 0.707 (evitar clipping)
    # Multiplicamos por 32767 e convertemos para int16
    signal_int16 = (signal * 32767).astype(np.int16)
    
    # Salva o arquivo WAV
    wav_write(filename, FS, signal_int16)
    print(f"Sinal AFSK salvo em '{filename}' (Taxa de Amostragem: {FS} Hz, Formato: 16-bit PCM)")

def transmit_text(message: str, user_id_tx: int, user_id_rx: int = 0, filename: str = "afsk_signal.wav"):
    """
    Função principal para construir, modular e salvar o sinal AFSK.
    """
    try:
        print(f"--- Transmissor AFSK (TX) ---")
        print(f"Mensagem a ser enviada: '{message}'")
        print(f"ID TX: {user_id_tx}, ID RX: {user_id_rx}")
        
        # 1. Construção do Pacote
        packet = build_packet(message, user_id_tx, user_id_rx)
        print(f"Pacote (Total {len(packet)} bytes): {packet.hex()}")
        
        # 2. Modulação
        signal = modulate_packet(packet)
        print(f"Sinal gerado (Total {len(signal)} amostras). Duração: {len(signal)/FS:.2f} segundos.")
        
        # 3. Salvamento do Sinal
        save_afsk_signal(signal, filename)
        
    except ValueError as e:
        print(f"Erro na transmissão: {e}")

if __name__ == '__main__':
    # Exemplo de uso
    transmit_text(
        message="OLA MUNDO!",
        user_id_tx=10,
        user_id_rx=20,
        filename="ola_mundo_afsk.wav"
    )
    
    # Exemplo de pacote mínimo (sem User_ID RX e CRC) - Apenas para demonstração de estrutura
    # Para o formato mínimo, o pacote seria: Preamble + Sync_Word + User_ID TX + Len + Payload
    # O código acima implementa o estendido, mas o TX mínimo é um subconjunto
    print("\n--- Exemplo de Pacote Mínimo (Estrutura) ---")
    message_min = "MIN"
    # O CRC é obrigatório no formato estendido, mas o requisito mínimo não o exige.
    # Para simplificar, o código acima gera o pacote estendido. A FSM no RX é que
    # decidirá se o CRC será checado.
    packet_min = build_packet(message_min, user_id_tx=1, user_id_rx=0)
    print(f"Pacote Estendido para 'MIN' (Total {len(packet_min)} bytes): {packet_min.hex()}")
    
    # Detalhe do pacote:
    # Preamble (4 bytes): aaaaaaaa
    # Sync Word (2 bytes): 2dd4
    # ID TX (1 byte): 01
    # ID RX (1 byte): 00
    # Len (1 byte): 03
    # Payload (3 bytes): 4d494e ('MIN')
    # CRC-16 (2 bytes): 4c75 (calculado)
    # Total: 4 + 2 + 1 + 1 + 1 + 3 + 2 = 14 bytes
    
    # O pacote gerado deve ser: aaaaaaaa2dd40100034d494e4c75
    
    # Teste de pacote com ID TX 1 e ID RX 0
    # ID TX: 1 (0x01), ID RX: 0 (0x00), Len: 3 (0x03)
    # Dados para CRC: 0100034d494e
    # CRC-16(0100034d494e) = 4c75
    # Pacote: aaaaaaaa2dd40100034d494e4c75
    
    print("Pacote esperado: aaaaaaaa2dd40100034d494e91ce")
    assert packet_min.hex() == "aaaaaaaa2dd40100034d494e91ce"
    print("Teste de Pacote Mínimo (Estrutura) OK.")
