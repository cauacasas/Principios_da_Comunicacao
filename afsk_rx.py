import numpy as np
from scipy.io import wavfile
from afsk_utils import (
    FS, SAMPLES_PER_BIT, F0, F1,
    PREAMBLE_BYTE, SYNC_WORD,
    bits_to_ascii, check_crc16_ccitt
)

# --- Constantes de Framing ---
PREAMBLE_BITS_LEN = 4 * 8  # 4 bytes * 8 bits/byte
SYNC_WORD_BITS_LEN = 2 * 8  # 2 bytes * 8 bits/byte
HEADER_FIXED_BITS_LEN = 5 * 8 # ID_TX (1) + ID_RX (1) + Len (1) + CRC (2) -> 5 bytes * 8 bits/byte

# --- Algoritmo de Goertzel ---

def goertzel_filter(samples: np.ndarray, target_freq: float) -> float:
    """
    Implementação do Algoritmo de Goertzel para estimar a energia na frequência alvo.
    
    Args:
        samples (np.ndarray): Amostras de áudio (um bloco de SAMPLES_PER_BIT).
        target_freq (float): Frequência alvo (F0 ou F1).
        
    Returns:
        float: Energia (magnitude quadrática) na frequência alvo.
    """
    N = len(samples)
    k = round((N * target_freq) / FS)
    
    # Se k for 0 ou N/2, o Goertzel não é ideal.
    if k == 0 or k >= N / 2:
        # Retorna 0 ou ajusta o N para evitar problemas
        return 0.0

    omega = (2.0 * np.pi * k) / N
    coeff = 2.0 * np.cos(omega)
    
    s_prev = 0.0
    s_prev2 = 0.0
    
    for sample in samples:
        s = sample + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
        
    # Magnitude quadrática
    power = s_prev2 * s_prev2 + s_prev * s_prev - coeff * s_prev * s_prev2
    return power

def demodulate_bit(samples: np.ndarray) -> int:
    """
    Demodula um bloco de amostras (um bit) usando o Algoritmo de Goertzel.
    Compara a energia em F0 e F1 para determinar o bit.
    """
    # Garante que o bloco tem o tamanho correto
    if len(samples) != SAMPLES_PER_BIT:
        # Isso pode acontecer no final do arquivo, ou se o sincronismo estiver errado
        return -1 # Indica erro de sincronismo/tamanho
        
    # Calcula a energia em F0 e F1
    power_f0 = goertzel_filter(samples, F0)
    power_f1 = goertzel_filter(samples, F1)
    
    # Compara as energias para determinar o bit
    if power_f0 > power_f1:
        return 0
    elif power_f1 > power_f0:
        return 1
    else:
        # Caso de empate (raro), pode indicar ruído ou sinal fraco
        return -2 # Indica indecisão

# --- Lógica de Recepção e Desempacotamento ---

def find_sync(bit_sequence: list[int], sync_word_bits: list[int]) -> int:
    """
    Busca a Sync Word na sequência de bits.
    Retorna o índice do bit imediatamente após a Sync Word, ou -1 se não encontrar.
    
    A busca deve começar após o preâmbulo.
    """
        # Converte a Sync Word para uma lista de bits para comparação
    sync_word_bits = [int(b) for b in format(SYNC_WORD, '016b')] # 16 bits
    
    # O padrão completo é Preamble (4 bytes) + Sync Word (2 bytes) = 6 bytes = 48 bits
    # O Preamble é 0xAA (10101010) repetido 4 vezes
    preamble_bits = [int(b) for b in format(PREAMBLE_BYTE, '08b')] * 4
    preamble_sync_pattern = preamble_bits + sync_word_bits
    pattern_len = len(preamble_sync_pattern)
    
    start_index = -1
    # A busca deve começar a partir do início da sequência de bits demodulados
    for i in range(len(bit_sequence) - pattern_len):
        # A busca deve ser exata, pois a demodulação já agrupou em bits
        if bit_sequence[i:i + pattern_len] == preamble_sync_pattern:
            # Retorna o índice do bit imediatamente após a Sync Word (o início do ID TX)
            start_index = i + pattern_len
            break
            
    return start_index

def unpack_packet(bit_sequence: list[int], my_user_id: int) -> tuple[str, bool, bool]:
    """
    Desempacota a sequência de bits a partir do início do pacote (após a Sync Word).
    
    Retorna: (mensagem_texto, crc_ok, addressed_to_me)
    """
    
    # O pacote começa após a Sync Word.
    # [User_ID TX (1)] [User_ID RX (1)] [Len (1)] [Payload (0-255)] [CRC-16 (2)]
    
    # 1. Extrai os campos fixos do cabeçalho
    # ID TX (8 bits), ID RX (8 bits), Len (8 bits)
    if len(bit_sequence) < 3 * 8:
        return "Erro: Pacote muito curto para o cabeçalho fixo.", False, False

    header_bits = bit_sequence[:3 * 8]
    
    # Converte os 3 bytes (ID_TX, ID_RX, Len)
    id_tx = int("".join(map(str, header_bits[0:8])), 2)
    id_rx = int("".join(map(str, header_bits[8:16])), 2)
    payload_len = int("".join(map(str, header_bits[16:24])), 2)
    
    print(f"  > ID TX: {id_tx}, ID RX: {id_rx}, Payload Len: {payload_len} bytes")
    
    # 2. Verifica Endereçamento (Formato Estendido)
    addressed_to_me = (id_rx == my_user_id)
    if not addressed_to_me:
        print(f"  > Pacote não endereçado a mim (Meu ID: {my_user_id}). Ignorando Payload.")
        return "", False, False # Retorna vazio se não for endereçado a mim
        
    # 3. Extrai Payload e CRC
    payload_bits_len = payload_len * 8
    crc_bits_len = 2 * 8
    
    expected_total_bits = 3 * 8 + payload_bits_len + crc_bits_len
    
    if len(bit_sequence) < expected_total_bits:
        return "Erro: Pacote truncado (tamanho menor que o esperado).", False, True

    # Bits do Payload
    payload_start = 3 * 8
    payload_end = payload_start + payload_bits_len
    payload_bits = bit_sequence[payload_start:payload_end]
    
    # Bits do CRC
    crc_start = payload_end
    crc_end = crc_start + crc_bits_len
    crc_bits = bit_sequence[crc_start:crc_end]
    
    # 4. Reconstrução do Texto
    message_text = bits_to_ascii(payload_bits)
    
    # 5. Verificação de Integridade (CRC)
    # Os dados para o CRC são: [ID TX (1)] [ID RX (1)] [Len (1)] [Payload (0-255)]
    data_for_crc_bits = header_bits + payload_bits
    
    # Converte a sequência de bits para bytes para a função CRC
    data_for_crc_bytes = bytes([int("".join(map(str, data_for_crc_bits[i:i+8])), 2) for i in range(0, len(data_for_crc_bits), 8)])
    
    # Converte o CRC recebido de bits para bytes (2 bytes)
    received_crc_bytes = bytes([int("".join(map(str, crc_bits[i:i+8])), 2) for i in range(0, len(crc_bits), 8)])
    
    crc_ok = check_crc16_ccitt(data_for_crc_bytes, received_crc_bytes)
    
    return message_text, crc_ok, addressed_to_me

def receive_afsk_signal(filename: str, my_user_id: int) -> tuple[str, bool, str]:
    """
    Função principal para ler, demodular e desempacotar o sinal AFSK.
    
    Retorna: (mensagem_texto, crc_ok, status_message)
    """
    print(f"--- Receptor AFSK (RX) ---")
    print(f"Lendo arquivo: '{filename}'")
    
    try:
        # 1. Leitura do Arquivo WAV
        # wavfile.read retorna (FS, data)
        # O FS lido deve ser 8000, mas usamos o FS fixo para o Goertzel
        fs_read, audio_data = wavfile.read(filename)
        
        # Converte para float64 (normalização para -1.0 a 1.0)
        audio_data = audio_data.astype(np.float64) / 32767.0
        
    except Exception as e:
        return "", False, f"Erro ao ler o arquivo WAV: {e}"

    # 2. Demodulação e Sincronismo de Bit (Simplificado)
    # Assumimos que a taxa de amostragem está correta.
    # O sincronismo de bit idealmente usaria o preâmbulo para ajustar o ponto de início
    # de cada bloco de SAMPLES_PER_BIT.
    
    demodulated_bits = []
    
    # Ponto de início de cada bit (idealmente ajustado pelo preâmbulo)
    # Aqui, fazemos uma demodulação "cega" (sem ajuste fino de fase/tempo)
    for i in range(0, len(audio_data), SAMPLES_PER_BIT):
        samples = audio_data[i:i + SAMPLES_PER_BIT]
        
        # Ignora o último bloco se for incompleto
        if len(samples) < SAMPLES_PER_BIT:
            continue
            
        bit = demodulate_bit(samples)
        
        # Ignora bits de erro (-1 ou -2)
        if bit >= 0:
            demodulated_bits.append(bit)
        
    print(f"  > Total de bits demodulados: {len(demodulated_bits)}")
    
    # 3. Busca pela Sync Word (Sincronismo de Pacote)
    # 3. Busca pelo Padrão Preamble + Sync Word (Sincronismo de Pacote)
    # A função find_sync agora busca o padrão completo e retorna o índice de início do ID TX
    start_index = find_sync(demodulated_bits, []) # O segundo argumento é ignorado, mas mantido para compatibilidade
            
    if start_index == -1:
        return "", False, "Erro: Não foi possível encontrar o padrão Preamble + Sync Word."
        
    print(f"  > Padrão Preamble+Sync encontrado. Início do pacote (ID TX) no bit: {start_index}")
    
    # 4. Desempacotamento
    packet_bits = demodulated_bits[start_index:]
    
    message_text, crc_ok, addressed_to_me = unpack_packet(packet_bits, my_user_id)
    
    if not addressed_to_me:
        return "", False, "Pacote recebido, mas não endereçado a este ID."
        
    if not crc_ok:
        return message_text, False, "Pacote recebido, mas falhou na verificação de CRC-16-CCITT."
        
    return message_text, True, "Pacote recebido e verificado com sucesso."

if __name__ == '__main__':
    # Exemplo de uso
    MY_ID = 20
    
    # O arquivo 'ola_mundo_afsk.wav' foi gerado pelo afsk_tx.py
    # O pacote é endereçado ao ID 20.
    
    message, crc_status, status = receive_afsk_signal("ola_mundo_afsk.wav", MY_ID)
    
    print("-" * 30)
    print(f"Status da Recepção: {status}")
    print(f"Mensagem: '{message}'")
    print(f"CRC OK: {crc_status}")
    
    # Teste com um arquivo que não é endereçado a mim (ex: ID 30)
    print("\n--- Teste de Endereçamento (ID 30) ---")
    message_not_mine, crc_status_not_mine, status_not_mine = receive_afsk_signal("ola_mundo_afsk.wav", 30)
    print(f"Status da Recepção: {status_not_mine}")
    print(f"Mensagem: '{message_not_mine}'")
    print(f"CRC OK: {crc_status_not_mine}")
