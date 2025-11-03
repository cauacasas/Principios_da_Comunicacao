import numpy as np
import crcmod.crcmod

# --- Especificações Técnicas (Tabela 2) ---
FS = 8000  # Taxa de amostragem (Hz)
BAUD_RATE = 300  # Taxa de símbolos (baud)
F0 = 2200  # Frequência para bit '0' (Hz)
F1 = 1200  # Frequência para bit '1' (Hz)
BITS_PER_SYMBOL = 1  # 2-FSK binária
SAMPLES_PER_BIT = FS // BAUD_RATE  # Número de amostras por bit

# --- Especificações de Framing (Tabela 3) ---
PREAMBLE_BYTE = 0xAA  # 10101010
SYNC_WORD = 0x2DD4  # 0010110111010100
CRC_POLY = 0x1021  # Polinômio CRC-16-CCITT (x^16 + x^12 + x^5 + 1)
CRC_INIT = 0xFFFF  # Valor inicial do CRC
CRC_XOROUT = 0x0000  # XOR de saída
CRC_REFIN = False  # Reflexão de entrada
CRC_REFOUT = False  # Reflexão de saída

# Objeto CRC-16-CCITT
crc16_ccitt = crcmod.crcmod.Crc(
    0x11021,  # 0x1021 << 1 (polinômio de 17 bits)
    initCrc=CRC_INIT,
    xorOut=CRC_XOROUT,
    rev=CRC_REFIN
)

# --- Funções de Utilidade ---

def ascii_to_bits(text: str) -> list[int]:
    """
    Converte uma string de texto ASCII em uma lista de bits (NRZ, MSB-first).
    Cada caractere é convertido em 8 bits.
    """
    bits = []
    for char in text:
        # Converte o caractere para seu valor ASCII (0-127)
        ascii_val = ord(char)
        
        # Converte o valor ASCII para uma string binária de 8 bits (MSB-first)
        # Ex: 'H' (72) -> '01001000'
        binary_string = format(ascii_val, '08b')
        
        # Adiciona os bits à lista
        bits.extend([int(b) for b in binary_string])
        
    return bits

def bits_to_ascii(bits: list[int]) -> str:
    """
    Converte uma lista de bits em uma string de texto ASCII.
    Os bits são agrupados em blocos de 8.
    """
    if len(bits) % 8 != 0:
        # Isso não deve acontecer em um pacote bem formado, mas é uma verificação de segurança
        print(f"Aviso: Número de bits ({len(bits)}) não é múltiplo de 8. Ignorando bits extras.")
        bits = bits[:-(len(bits) % 8)]

    text = []
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i+8]
        
        # Converte a lista de bits em uma string binária
        binary_string = "".join(map(str, byte_bits))
        
        # Converte a string binária para um inteiro
        ascii_val = int(binary_string, 2)
        
        # Converte o inteiro para o caractere ASCII
        text.append(chr(ascii_val))
        
    return "".join(text)

def generate_tone(frequency: float, duration_seconds: float) -> np.ndarray:
    """
    Gera um sinal senoidal de uma dada frequência e duração.
    """
    t = np.linspace(0, duration_seconds, int(FS * duration_seconds), endpoint=False)
    # Gera a senoide e normaliza para evitar clipping (máximo -3 dBFS = 0.707)
    # O sinal é gerado em ponto flutuante, que será convertido para 16-bit PCM depois.
    amplitude = 0.707
    return amplitude * np.sin(2 * np.pi * frequency * t)

def calculate_crc16_ccitt(data_bytes: bytes) -> bytes:
    """
    Calcula o CRC-16-CCITT (X.25) de um bloco de bytes.
    Retorna o CRC como 2 bytes (MSB primeiro).
    """
    # O objeto crc16_ccitt já está configurado
    crc_value = crc16_ccitt.crcValue
    
    # Atualiza o CRC com os dados
    crc_value = crc16_ccitt.new(data_bytes).crcValue
    
    # Retorna o CRC como 2 bytes (MSB primeiro)
    return crc_value.to_bytes(2, byteorder='big')

def check_crc16_ccitt(data_bytes: bytes, received_crc: bytes) -> bool:
    """
    Verifica se o CRC calculado para data_bytes corresponde ao received_crc.
    """
    calculated_crc = calculate_crc16_ccitt(data_bytes)
    return calculated_crc == received_crc

# --- Funções de Modulação e Demodulação (Esboços Iniciais) ---

def modulate_bit(bit: int) -> np.ndarray:
    """
    Gera as amostras de áudio para um único bit (0 ou 1).
    """
    duration = SAMPLES_PER_BIT / FS
    if bit == 0:
        return generate_tone(F0, duration)
    elif bit == 1:
        return generate_tone(F1, duration)
    else:
        raise ValueError("O bit deve ser 0 ou 1")

def demodulate_bit(samples: np.ndarray) -> int:
    """
    Demodula um bloco de amostras para recuperar o bit (0 ou 1).
    Esta é uma função placeholder que será implementada na Fase 4 com Goertzel.
    """
    # Placeholder: Implementação real na Fase 4
    # Por enquanto, retorna um valor aleatório ou 0 para fins de teste de fluxo
    return 0 

if __name__ == '__main__':
    # Teste de conversão ASCII-Bits
    test_string = "HELLO"
    bits = ascii_to_bits(test_string)
    print(f"Texto original: {test_string}")
    print(f"Bits (MSB-first): {''.join(map(str, bits))}")
    
    # Teste de conversão Bits-ASCII
    reconstructed_text = bits_to_ascii(bits)
    print(f"Texto reconstruído: {reconstructed_text}")
    print("-" * 20)
    
    # Teste de Geração de Tom (Salvar em WAV para verificação manual)
    # Requer `scipy.io.wavfile` que será adicionado no módulo TX
    
    # Teste de CRC-16-CCITT
    data = b'123456789'
    crc_calculated = calculate_crc16_ccitt(data)
    print(f"Dados: {data}")
    print(f"CRC-16-CCITT calculado: {crc_calculated.hex()}") # Deve ser '29b1'
    
    # Teste de verificação de CRC
    is_valid = check_crc16_ccitt(data, crc_calculated)
    print(f"Verificação de CRC (válido): {is_valid}")
    
    # Teste de verificação de CRC com erro
    invalid_crc = b'\x00\x00'
    is_invalid = check_crc16_ccitt(data, invalid_crc)
    print(f"Verificação de CRC (inválido): {is_invalid}")
    
    # Verificação de parâmetros
    print("-" * 20)
    print(f"Taxa de Amostragem (FS): {FS} Hz")
    print(f"Taxa de Símbolos (Baud Rate): {BAUD_RATE} baud")
    print(f"Amostras por Bit: {SAMPLES_PER_BIT}")
    print(f"Duração de 1 Bit: {SAMPLES_PER_BIT/FS:.4f} s")
    print(f"Frequência Bit 0: {F0} Hz")
    print(f"Frequência Bit 1: {F1} Hz")
