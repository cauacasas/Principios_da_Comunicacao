# Principios da Comunicação

# Sistema de Modulação e Demodulação AFSK em Python

Este projeto implementa um sistema completo de modulação e demodulação **Audio Frequency Shift Keying (AFSK)** em banda base, conforme as especificações técnicas da Prática 2 de Princípios de Comunicações. O sistema é capaz de transmitir e receber dados digitais (strings de texto) simulando um canal acústico através de arquivos WAV.

## 1. Especificações Técnicas (Tabela 2 do Documento)

| Parâmetro | Valor / Descrição |
| :--- | :--- |
| **Taxa de amostragem (Fs)** | 8000 Hz |
| **Taxa de símbolos (Baud Rate)** | 300 baud |
| **Frequência para bit "0" (F0)** | 2200 Hz |
| **Frequência para bit "1" (F1)** | 1200 Hz |
| **Tipo de modulação** | 2-FSK (AFSK) binária |
| **Codificação dos bits** | NRZ, MSB-first |
| **Sincronismo** | Preâmbulo (4 bytes de 0xAA) e Sync Word (0x2DD4) |
| **Verificação de integridade** | CRC-16-CCITT (para o pacote estendido) |
| **Formato do áudio** | Mono, 8 kHz, 16 bits PCM (.wav) |

## 2. Estrutura do Pacote (Framing - Formato Estendido)

O sistema implementa o **Formato Estendido**, que garante o endereçamento (acesso múltiplo) e a verificação de integridade (CRC-16-CCITT).

| Campo | Tamanho | Descrição |
| :--- | :--- | :--- |
| **Preamble** | 4 bytes | `0xAA` repetido para sincronismo de bit. |
| **Sync_Word** | 2 bytes | `0x2DD4` para sincronismo de pacote. |
| **User_ID TX** | 1 byte | Identificador do remetente. |
| **User_ID RX** | 1 byte | Identificador do destinatário (endereçamento). |
| **Len** | 1 byte | Número de bytes úteis no campo Payload (0-255). |
| **Payload** | 0-255 bytes | Mensagem em texto string (ASCII). |
| **CRC-16** | 2 bytes | Código de verificação CRC-16-CCITT. |

## 3. Estrutura do Código

O projeto está organizado em três arquivos Python principais:

1.  `afsk_utils.py`: Contém constantes de configuração, funções de conversão (ASCII para bits e vice-versa), geração de tons senoidais e o cálculo/verificação do CRC-16-CCITT.
2.  `afsk_tx.py`: Módulo de Transmissão. Responsável pela construção do pacote (`build_packet`), modulação AFSK (`modulate_packet`) e salvamento do sinal em arquivo WAV.
3.  `afsk_rx.py`: Módulo de Recepção. Implementa o Algoritmo de Goertzel para detecção de frequência, a lógica de busca do padrão Preâmbulo+Sync Word, demodulação de bits e desempacotamento/verificação do CRC.
4.  `afsk_system.py`: Implementa a Máquina de Estados Finitos (FSM) e a interface de terminal interativa para simulação de transmissão (TX) e recepção (RX) via arquivos WAV.

## 4. Pré-requisitos

O projeto requer as seguintes bibliotecas Python:

```bash
pip3 install numpy scipy crcmod
```

## 5. Instruções de Uso (Simulação)

Devido às limitações do ambiente sandbox, o sistema simula a comunicação half-duplex utilizando arquivos WAV.

### 5.1. Inicialização

Execute o arquivo principal para iniciar a interface de terminal:

```bash
python3 afsk_system.py
```

O sistema iniciará no estado `[IDLE]`.

### 5.2. Simulação de Transmissão (TX)

1.  No prompt, digite `t` e pressione Enter.
2.  Digite a mensagem de texto e pressione Enter.
3.  Digite o ID do destinatário (um número de 0 a 255) e pressione Enter.
4.  O sistema irá construir o pacote, modular o sinal AFSK e salvar o resultado em um arquivo WAV com um nome no formato `tx_id_XX_to_rx_id_YY_timestamp.wav`.

### 5.3. Simulação de Recepção (RX)

1.  No prompt, digite `r` e pressione Enter.
2.  O sistema pedirá o nome do arquivo WAV a ser lido (use o arquivo gerado na etapa de TX).
3.  O módulo RX fará a leitura, demodulação (Goertzel), busca por Preâmbulo+Sync Word, desempacotamento e verificação de CRC.
4.  O resultado (mensagem, status do CRC e status do endereçamento) será exibido no terminal.

**Nota sobre Endereçamento:** O `afsk_system.py` está configurado com `MY_ID = 20` (padrão). Se o pacote lido tiver `User_ID RX` diferente de 20, a mensagem será ignorada, simulando o acesso múltiplo. Para testar a recepção, o `User_ID RX` do pacote deve ser igual ao `MY_ID` do sistema.

## 6. Exemplo de Teste de Ponta a Ponta

1.  **Transmissão (Com MY_ID=10):**
    *   Comando: `t`
    *   Mensagem: `Teste AFSK`
    *   ID Destinatário: `20`
    *   Resultado: Arquivo `tx_id_10_to_rx_id_20_TIMESTAMP.wav` gerado.
2.  **Recepção (Com MY_ID=20):**
    *   Comando: `r`
    *   Arquivo: `tx_id_10_to_rx_id_20_TIMESTAMP.wav`
    *   Resultado:
        ```
        --- Resultado da Recepção ---
        Status: Pacote recebido e verificado com sucesso.
        Mensagem Recebida: 'Teste AFSK'
        Verificação de Integridade (CRC OK): True
        -----------------------------
        ```
3.  **Teste de Endereçamento (Com MY_ID=30):**
    *   Comando: `r`
    *   Arquivo: `tx_id_10_to_rx_id_20_TIMESTAMP.wav`
    *   Resultado:
        ```
        --- Resultado da Recepção ---
        Status: Pacote recebido, mas não endereçado a este ID.
        Verificação de Integridade (CRC OK): False
        -----------------------------
        ```
