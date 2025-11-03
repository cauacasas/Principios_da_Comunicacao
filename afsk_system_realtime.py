import time
import numpy as np
import sounddevice as sd
import threading
from afsk_tx import build_packet, modulate_packet
from afsk_rx import demodulate_bit, find_sync, unpack_packet
from afsk_utils import FS, SAMPLES_PER_BIT, PREAMBLE_BYTE, SYNC_WORD

# --- Configurações do Sistema ---
MY_ID = 10 # ID do usuário (pode ser alterado)
CHUNK_SIZE = SAMPLES_PER_BIT * 4 # Processa 4 bits por vez para detecção de portadora/preâmbulo
TIMEOUT_SECONDS = 10 # Tempo máximo de espera por um pacote

# --- FSM Estados ---
STATE_IDLE = 0
STATE_TX_READY = 1
STATE_TX_SENDING = 2
STATE_RX_WAIT_PREAMBLE = 3
STATE_RX_RECEIVING = 4
STATE_RX_FINISHED = 5

# --- Funções de Áudio em Tempo Real ---

def play_signal(signal: np.ndarray):
    """
    Reproduz o sinal de áudio usando sounddevice.
    """
    # Converte o sinal de float (-1.0 a 1.0) para int16 (-32768 a 32767)
    signal_int16 = (signal * 32767).astype(np.int16)
    sd.play(signal_int16, samplerate=FS)
    sd.wait() # Espera a reprodução terminar

# --- FSM Principal ---

def afsk_fsm():
    """
    Máquina de Estados Finitos para controle do sistema AFSK (Half-Duplex) em tempo real.
    """
    current_state = STATE_IDLE
    
    # Variáveis de estado
    message = ""
    target_id = 0
    packet_to_send = None
    signal_to_send = None
    
    # Variáveis de RX
    demodulated_bits = []
    
    # --- Loop Principal ---
    while True:
        
        # --- STATE_IDLE ---
        if current_state == STATE_IDLE:
            print("\n[IDLE] Sistema em espera.")
            user_input = input(f"Comando (Meu ID: {MY_ID}) - 't' para TX, 'r' para RX, 'q' para sair: ").strip().lower()
            
            if user_input == 'q':
                print("[IDLE] Encerrando o sistema.")
                break
            elif user_input == 't':
                message = input("Digite a mensagem: ")
                try:
                    target_id = int(input("Digite o ID do destinatário (0-255): "))
                except ValueError:
                    print("[IDLE] ID do destinatário inválido. Voltando ao IDLE.")
                    continue
                current_state = STATE_TX_READY
            elif user_input == 'r':
                current_state = STATE_RX_WAIT_PREAMBLE
            else:
                print("[IDLE] Comando inválido.")
                
        # --- STATE_TX_READY ---
        elif current_state == STATE_TX_READY:
            print(f"[TX_READY] Preparando pacote para '{message}' (TX ID: {MY_ID}, RX ID: {target_id}).")
            
            try:
                packet_to_send = build_packet(message, MY_ID, target_id)
                signal_to_send = modulate_packet(packet_to_send)
                
                print(f"[TX_READY] Pacote pronto. Duração: {len(signal_to_send)/FS:.2f}s.")
                current_state = STATE_TX_SENDING
                
            except ValueError as e:
                print(f"[TX_READY] Erro ao construir o pacote: {e}")
                current_state = STATE_IDLE
                
        # --- STATE_TX_SENDING ---
        elif current_state == STATE_TX_SENDING:
            print("[TX_SENDING] Transmitindo sinal em tempo real...")
            play_signal(signal_to_send)
            print("[TX_SENDING] Transmissão concluída.")
            
            # Limpa variáveis de estado e volta ao IDLE
            packet_to_send = None
            signal_to_send = None
            message = ""
            target_id = 0
            current_state = STATE_IDLE
            
        # --- STATE_RX_WAIT_PREAMBLE (Escuta Contínua) ---
        elif current_state == STATE_RX_WAIT_PREAMBLE:
            print(f"[RX_WAIT_PREAMBLE] Escutando o canal (Meu ID: {MY_ID}). Pressione Ctrl+C para parar.")
            
            # Variáveis para o buffer de recepção
            demodulated_bits = []
            
            # Buffer de amostras para sincronismo de bit
            sample_buffer = np.array([], dtype=np.float64)
            
            # Padrão completo Preamble + Sync Word (48 bits)
            sync_word_bits = [int(b) for b in format(SYNC_WORD, '016b')]
            preamble_bits = [int(b) for b in format(PREAMBLE_BYTE, '08b')] * 4
            preamble_sync_pattern = preamble_bits + sync_word_bits
            pattern_len = len(preamble_sync_pattern)
            
            # Inicia o stream de entrada de áudio
            try:
                with sd.InputStream(samplerate=FS, channels=1, dtype='int16') as stream:
                    print("  > Stream de áudio iniciado. Aguardando sinal...")
                    
                    # Loop de escuta contínua
                    while current_state == STATE_RX_WAIT_PREAMBLE:
                        # Lê um bloco de amostras
                        recording, overflowed = stream.read(CHUNK_SIZE)
                        
                        # Converte para float64 (normalização para -1.0 a 1.0)
                        samples = recording.flatten().astype(np.float64) / 32767.0
                        
                        # Adiciona ao buffer de amostras
                        sample_buffer = np.concatenate((sample_buffer, samples))
                        
                        # Processa o buffer em blocos de SAMPLES_PER_BIT
                        while len(sample_buffer) >= SAMPLES_PER_BIT:
                            bit_samples = sample_buffer[:SAMPLES_PER_BIT]
                            sample_buffer = sample_buffer[SAMPLES_PER_BIT:]
                            
                            bit = demodulate_bit(bit_samples)
                            
                            if bit >= 0:
                                demodulated_bits.append(bit)
                                
                                # Verifica se o padrão Preamble+Sync está no final dos bits demodulados
                                if len(demodulated_bits) >= pattern_len:
                                    # Verifica se o último bloco de bits corresponde ao padrão
                                    if demodulated_bits[-pattern_len:] == preamble_sync_pattern:
                                        print("\n[RX_WAIT_PREAMBLE] Padrão Preamble+Sync detectado!")
                                        current_state = STATE_RX_RECEIVING
                                        break # Sai do loop while len(sample_buffer)
                        
                        if current_state == STATE_RX_RECEIVING:
                            break # Sai do loop while current_state == STATE_RX_WAIT_PREAMBLE
                        
            except KeyboardInterrupt:
                print("\n[RX_WAIT_PREAMBLE] Interrompido pelo usuário.")
                current_state = STATE_IDLE
            except Exception as e:
                print(f"\n[RX_WAIT_PREAMBLE] Erro no stream de áudio: {e}")
                current_state = STATE_IDLE
                
        # --- STATE_RX_RECEIVING (Recebe o restante do pacote) ---
        elif current_state == STATE_RX_RECEIVING:
            print("[RX_RECEIVING] Recebendo o restante do pacote...")
            
            # O pacote começa imediatamente após o Preamble+Sync Word
            start_index = len(demodulated_bits) # O índice do primeiro bit do ID TX
            
            # O tamanho do pacote (em bytes) é desconhecido, então precisamos ler o campo Len
            # O cabeçalho fixo (ID TX, ID RX, Len) tem 3 bytes = 24 bits
            
            # O stream de áudio já está fechado, então precisamos de uma forma de ler o restante
            # Para simplificar, vamos assumir que o pacote inteiro foi recebido no buffer
            # ou que o RX real continuaria lendo até o timeout.
            
            # Como o RX_WAIT_PREAMBLE já fez a demodulação, vamos processar o buffer de bits
            
            # 1. Desempacotamento
            packet_bits = demodulated_bits[start_index:]
            
            # Para o teste real, você precisará de uma lógica de timeout e de buffer
            # para garantir que o pacote inteiro seja recebido.
            
            # Aqui, vamos assumir que o pacote inteiro está no buffer de bits.
            
            # Tenta extrair o cabeçalho fixo (3 bytes = 24 bits)
            if len(packet_bits) < 24:
                print("[RX_RECEIVING] Erro: Pacote muito curto para o cabeçalho fixo.")
                current_state = STATE_IDLE
                continue
                
            header_bits = packet_bits[:24]
            payload_len = int("".join(map(str, header_bits[16:24])), 2)
            
            # O tamanho total do pacote (após Sync Word) é:
            # ID TX (1) + ID RX (1) + Len (1) + Payload (Len) + CRC (2)
            expected_total_bits = (3 + payload_len + 2) * 8
            
            if len(packet_bits) < expected_total_bits:
                print(f"[RX_RECEIVING] Erro: Pacote truncado. Esperado: {expected_total_bits} bits, Recebido: {len(packet_bits)} bits.")
                current_state = STATE_IDLE
                continue
                
            # Processa o pacote completo
            message_text, crc_ok, addressed_to_me = unpack_packet(packet_bits[:expected_total_bits], MY_ID)
            
            print("\n--- Resultado da Recepção ---")
            print(f"Status: {'Pacote recebido e verificado com sucesso.' if crc_ok and addressed_to_me else 'Falha na Recepção.'}")
            if message_text:
                print(f"Mensagem Recebida: '{message_text}'")
            print(f"Verificação de Integridade (CRC OK): {crc_ok}")
            print(f"Endereçado a mim: {addressed_to_me}")
            print("-----------------------------\n")
            
            current_state = STATE_IDLE
            
        # --- Outros estados RX (simplificados) ---
        elif current_state == STATE_RX_FINISHED:
            current_state = STATE_IDLE
            
# --- Função de Inicialização ---
def run_terminal():
    """
    Interface de terminal para o sistema AFSK.
    """
    print("--- Sistema AFSK (Audio Frequency Shift Keying) - TEMPO REAL ---")
    print(f"Meu ID de Usuário: {MY_ID}")
    print("Modo de Operação: Half-Duplex (TX/RX - Tempo Real via sounddevice)")
    print("Atenção: Requer a biblioteca 'sounddevice' e acesso ao microfone/alto-falante.")
    
    try:
        afsk_fsm()
    except OSError as e:
        print(f"\nERRO: Falha ao iniciar o sounddevice. Verifique se o PortAudio está instalado e se o microfone/alto-falante estão configurados.")
        print(f"Detalhes do erro: {e}")

if __name__ == '__main__':
    run_terminal()
