import time
import numpy as np
from afsk_tx import build_packet, modulate_packet, save_afsk_signal
from afsk_rx import receive_afsk_signal
from afsk_utils import FS

# --- Configurações do Sistema ---
MY_ID = 20 # ID do usuário (pode ser alterado)

# --- FSM Estados ---
STATE_IDLE = 0
STATE_TX_READY = 1
STATE_TX_SENDING = 2
STATE_RX_WAIT_PREAMBLE = 3

# --- FSM Principal ---

def afsk_fsm():
    """
    Máquina de Estados Finitos para controle do sistema AFSK (Half-Duplex).
    Implementada como interface de terminal interativa, simulando TX/RX via arquivos WAV.
    """
    current_state = STATE_IDLE
    
    # Variáveis de estado
    message = ""
    target_id = 0
    packet_to_send = None
    signal_to_send = None
    
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
                # Garante que o ID seja um inteiro
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
                # 1. Construção do Pacote
                packet_to_send = build_packet(message, MY_ID, target_id)
                
                # 2. Modulação
                signal_to_send = modulate_packet(packet_to_send)
                
                print(f"[TX_READY] Pacote pronto. Duração: {len(signal_to_send)/FS:.2f}s.")
                current_state = STATE_TX_SENDING
                
            except ValueError as e:
                print(f"[TX_READY] Erro ao construir o pacote: {e}")
                current_state = STATE_IDLE
                
        # --- STATE_TX_SENDING ---
        elif current_state == STATE_TX_SENDING:
            print("[TX_SENDING] Transmitindo sinal (Simulação: Salvando em WAV)...")
            # Cria um nome de arquivo único
            filename = f"tx_id_{MY_ID}_to_rx_id_{target_id}_{int(time.time())}.wav"
            
            # Simula a transmissão salvando o sinal
            save_afsk_signal(signal_to_send, filename)
            
            print("[TX_SENDING] Transmissão concluída.")
            
            # Limpa variáveis de estado e volta ao IDLE
            packet_to_send = None
            signal_to_send = None
            message = ""
            target_id = 0
            current_state = STATE_IDLE
            
        # --- STATE_RX_WAIT_PREAMBLE ---
        elif current_state == STATE_RX_WAIT_PREAMBLE:
            print("[RX_WAIT_PREAMBLE] Simulação de Recepção (Lendo Arquivo WAV)...")
            
            filename = input("Digite o nome do arquivo WAV a ser lido (ex: ola_mundo_afsk.wav): ")
            
            # A função receive_afsk_signal faz toda a lógica de demodulação, sincronismo e desempacotamento
            message_text, crc_ok, status_message = receive_afsk_signal(filename, MY_ID)
            
            print("\n--- Resultado da Recepção ---")
            print(f"Status: {status_message}")
            if message_text:
                print(f"Mensagem Recebida: '{message_text}'")
            print(f"Verificação de Integridade (CRC OK): {crc_ok}")
            print("-----------------------------\n")
            
            current_state = STATE_IDLE
            
# --- Função de Inicialização ---
def run_terminal():
    """
    Interface de terminal para o sistema AFSK.
    """
    print("--- Sistema AFSK (Audio Frequency Shift Keying) ---")
    print(f"Meu ID de Usuário: {MY_ID}")
    print("Modo de Operação: Half-Duplex (TX/RX - Simulação via Arquivos WAV)")
    print("Atenção: A I/O de áudio em tempo real não é suportada neste ambiente.")
    print("  > 't' (TX) salva o sinal em um arquivo WAV.")
    print("  > 'r' (RX) lê um arquivo WAV para demodulação.")
    
    afsk_fsm()

if __name__ == '__main__':
    run_terminal()
