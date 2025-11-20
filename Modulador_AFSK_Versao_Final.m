% ---------------------------------------------------------------------------
% Modulador AFSK
% Projeto Prática 2 – Princípios de Comunicações – SENAI CIMATEC
%
% FS = 8000 Hz | BAUDRATE = 500 | SPS = 16 | F1=1200 Hz | F0=2200 Hz
% - Framing: PREAMBLE + SYNC WORD + UIDTX + UIDRX + LEN + PAYLOAD + CRC
% ---------------------------------------------------------------------------

%% -------------------- Inicialização --------------------
clear;                      % limpa workspace
clc;                        % limpa janela de comandos
close all;                  % fecha figuras abertas

% --- PARÂMETROS GLOBAIS (Tabela 2 do roteiro) -------------------------
SAMPLE_RATE = 8000;   % Frequência de amostragem (Hz)
BAUD_RATE   = 500;    % Taxa de símbolos (baud) -> ajustado para SPS inteiro
FREQ_BIT_1  = 1200;   % Frequência usada para bit 1 (AFSK)
FREQ_BIT_0  = 2200;   % Frequência usada para bit 0 (AFSK)
AUDIO_LEVEL = 0.5;    % Nível do áudio, recomendado evitar clipping
OUTPUT_FILENAME = 'SinalModulado.wav';  % Arquivo gerado

% --- PARÂMETROS DERIVADOS --------------------------------------------
% SPS = Samples per Symbol = Fs / BaudRate
% Deve ser inteiro para evitar distorção temporal e facilitar demodulação
SAMPLES_PER_SYMBOL = round(SAMPLE_RATE / BAUD_RATE);  % Aqui = 16
fprintf('\n[SPS] Samples por símbolo: %d\n', SAMPLES_PER_SYMBOL);


% --- ENTRADA DE DADOS E VALIDAÇÃO DE IDs (Formato estendido) ----------
% Campo: UIDTX, UIDRX e LEN estão na estrutura de frame da Tabela 3
disp('--- 📡 Gerador de .WAV AFSK (CPFSK Corrigido) ---');
message = input('Mensagem (String ASCII): ', 's');

while true
    uid_tx = input('Seu ID (UIDTX, 0-255): ');
    uid_rx = input('ID do Destinatário (UIDRX, 0-255): ');

    % Função de validação para permitir múltiplos usuários (Acesso múltiplo – roteiro)
    is_valid_id = @(id) isnumeric(id) && isscalar(id) && ...
                         (id >= 0) && (id <= 255) && (floor(id) == id);

    % Proteção de entrada do usuário
    if ~is_valid_id(uid_tx)
        fprintf('\n[ERRO] UIDTX inválido. Deve estar entre 0–255.\n\n');
        continue;
    end
    if ~is_valid_id(uid_rx)
        fprintf('\n[ERRO] UIDRX inválido. Deve estar entre 0–255.\n\n');
        continue;
    end
    if uid_tx == uid_rx
        fprintf('\n[ERRO] TX e RX devem ser diferentes.\n\n');
        continue;
    end

    fprintf('--- IDs validados (TX: %d, RX: %d) ---\n', uid_tx, uid_rx);
    break;
end


% --- Construção do PACOTE (Frame completo–Tabela 3–Formato estendido) -
fprintf('\nConstruindo pacote...\n');
try
    % Implementação da camada de framing
    packet_bytes = build_packet(message, uid_tx, uid_rx);

    % Impressão do pacote para depuração (requisito do relatório)
    fprintf('Pacote em HEX: %s\n', dec2hex(packet_bytes, 2)');

    % ----------------- PREPARAR BITSTREAM PARA PLOT ---------------------
    % Reconstrói bit_stream (MSB-first) a partir do packet_bytes para plot
    total_bits = length(packet_bytes) * 8;
    bit_stream = zeros(total_bits,1);
    bit_idx = 1;
    for i = 1:length(packet_bytes)
        byte = packet_bytes(i);
        for k = 7:-1:0
            bit_stream(bit_idx) = double(bitand(bitshift(byte, -k), 1));
            bit_idx = bit_idx + 1;
        end
    end

    % --- MODULAÇÃO AFSK COM CPFSK -------------------------------------
    fprintf('Modulando sinal de áudio (CPFSK)...\n');
    full_audio_signal = modulate_packet_cplx(packet_bytes, SAMPLE_RATE, ...
        FREQ_BIT_1, FREQ_BIT_0, SAMPLES_PER_SYMBOL, AUDIO_LEVEL);

    % Adiciona silêncio final para não cortar áudio
    silence = zeros(round(SAMPLE_RATE * 0.5), 1);
    full_audio_signal = [full_audio_signal; silence];

    audio_duration_sec = length(full_audio_signal) / SAMPLE_RATE;
    fprintf('Sinal modulado gerado. Duração: %.2f segundos.\n', audio_duration_sec);

    % --- 6. SALVAR EM .WAV (Requisito da prática - Etapa 1)
    fprintf('Salvando o arquivo "%s"...\n', OUTPUT_FILENAME);
    audiowrite(OUTPUT_FILENAME, full_audio_signal, SAMPLE_RATE);
    fprintf('Arquivo .wav salvo com sucesso!\n');

    % ===================== PLOTS SOLICITADOS (ANTES DE OUVIR) =============
    % Plot do sinal no tempo
    figure;
    t = (0:length(full_audio_signal)-1)/SAMPLE_RATE;
    plot(t, full_audio_signal);
    xlabel('Tempo (s)');
    ylabel('Amplitude');
    title('Sinal AFSK Modulado no Tempo');
    grid on;

    % FFT do sinal
    N = length(full_audio_signal);
    Y = fft(full_audio_signal);
    Ymag = abs(Y) / N;
    f = (0:N-1) * SAMPLE_RATE / N;

    figure;
    plot(f(1:floor(N/2)), Ymag(1:floor(N/2)));
    xlabel('Frequência (Hz)');
    ylabel('Magnitude');
    title('FFT do Sinal AFSK');
    xlim([0 4000]);
    grid on;

    % Plot do bitstream (binário)
    figure;
    stairs(bit_stream, 'LineWidth', 1.2); hold on;
    plot(bit_stream, 'ko', 'MarkerSize', 3, 'MarkerFaceColor','k');
    ylim([-0.3 1.3]);
    yticks([0 1]); yticklabels({'0','1'});
    xlabel('Índice do bit');
    ylabel('Valor');
    title('Bitstream Gerado (MSB-first)');
    grid on;
    % ===================== FIM DOS PLOTS =================================

    % --- 7. Reprodução com audioplayer 
    resposta = input('\nOuvir o sinal? (sim/nao): ', 's');
    querOuvir = strcmpi(resposta, 'sim');

    if querOuvir
        fprintf('Inicializando player...\n');
        try
            player = audioplayer(full_audio_signal, SAMPLE_RATE);
            while querOuvir
                fprintf('--- 🎧 Reproduzindo áudio ---\n');
                playblocking(player); % Bloqueia até o áudio terminar

                resposta_repetir = input('Repetir? (sim/nao): ', 's');
                if ~strcmpi(resposta_repetir, 'sim')
                    querOuvir = false;
                end
            end
        catch e_audio
            fprintf('Erro no audioplayer: %s\n', e_audio.message);
        end
    end

catch e
    fprintf('Erro: %s\n', e.message);
end



% =========================================================================
% FUNÇÕES AUXILIARES – Implementações do Frame, Codificação e Modulação
% =========================================================================

% --- Criação do frame completo com CRC 
function packet = build_packet(message, uid_tx, uid_rx)

    % Campos de sincronismo
    PREAMBLE = repmat(uint8(hex2dec('AA')), 1, 4);      % 0xAA 0xAA 0xAA 0xAA
    SYNC_WORD = uint8([hex2dec('2D'), hex2dec('D4')]);  % Palavra fixa de sync

    % Constrói campos do protocolo
    payload = uint8(message);                           % ASCII texto
    header  = uint8([uid_tx, uid_rx, length(payload)]); % Identificação + tamanho

    % CRC deve ser calculado sobre header + payload
    data_to_crc = [header, payload];
    crc_val = crc16_ccitt(data_to_crc);                % Código de integridade
    crc_bytes = typecast(swapbytes(uint16(crc_val)), 'uint8');

    % Concatenação do frame completo
    packet = [PREAMBLE, SYNC_WORD, data_to_crc, crc_bytes];
end


% --- MODULAÇÃO CPFSK
% Mantida com assinatura ORIGINAL (retorna apenas audio_out)
function audio_out = modulate_packet_cplx(packet_bytes, fs, f1, f0, sps, level)

    % Expansão dos bytes para bits MSB–first
    total_bits = length(packet_bytes) * 8;
    bit_stream_local = zeros(total_bits, 1);
    bit_idx = 1;

    for i = 1:length(packet_bytes)
        byte = packet_bytes(i);
        for k = 7:-1:0
            bit_stream_local(bit_idx) = double(bitand(bitshift(byte, -k), 1));
            bit_idx = bit_idx + 1;
        end
    end

    % Mapeamento FSK (bit=1->f1, bit=0->f0)
    freq_stream = (bit_stream_local * f1) + ((1-bit_stream_local) * f0);

    % Repetição dos tons para cada símbolo
    freq_samples = kron(freq_stream, ones(sps, 1));

    % CPFSK: integração para manter continuidade de fase
    phase = cumsum(2.0 * pi * freq_samples / fs);

    % Geração da senoide modulada
    audio_out = level * sin(phase);
    audio_out = audio_out(:);
end


% --- CRC-16-CCITT
function crc = crc16_ccitt(data)
    crc = uint16(hex2dec('FFFF'));
    poly = uint16(hex2dec('1021'));

    for i = 1:length(data)
        byte = uint16(data(i));
        crc = bitxor(crc, bitshift(byte, 8));
        for j = 1:8
            if bitand(crc, hex2dec('8000'))
                crc = bitxor(bitshift(crc, 1), poly);
            else
                crc = bitshift(crc, 1);
            end
        end
    end
    crc = bitand(crc, hex2dec('FFFF'));
end
