% -----------------------------------------------------------------------------
% DEMODULADOR AFSK — Versão Final
% FS = 8000 Hz | BAUDRATE = 500 | SPS = 16 | F1=1200 Hz | F0=2200 Hz
% -----------------------------------------------------------------------------

%% -------------------- Inicialização --------------------
clear;                      % limpa workspace
clc;                        % limpa janela de comandos
close all;                  % fecha figuras abertas

%% -------------------- Parâmetros principais --------------------
SAMPLE_RATE = 8000;         % taxa de amostragem (Hz)
BAUD_RATE   = 500;          % símbolos por segundo (baud)
FREQ_BIT_1  = 1200;         % tom representando bit '1' (Hz)
FREQ_BIT_0  = 2200;         % tom representando bit '0' (Hz)
SPS = round(SAMPLE_RATE / BAUD_RATE);  % amostras por símbolo (deve ser inteiro)
fprintf('[INFO] SAMPLE_RATE=%d Hz | BAUD_RATE=%d | SPS=%d\n', SAMPLE_RATE, BAUD_RATE, SPS);

OUTPUT_WAV = 'SinalModuladoComCanal.wav';   % arquivo WAV de saída (opcional)
SYNC_WORD_VAL = hex2dec('2DD4');       % palavra de sincronismo (0x2DD4)

%% -------------------- FSM: estados numéricos --------------------
STATE_SEARCHING_SYNC  = 1;  % procurar SYNC
STATE_READING_HEADER  = 2;  % ler header (3 bytes)
STATE_READING_PAYLOAD = 3;  % ler payload (LEN bytes)
STATE_READING_CRC     = 4;  % ler CRC (2 bytes)
STATE_VALIDATING      = 5;  % validar CRC

%% -------------------- Pré-cálculo Goertzel --------------------
% calcula coeficientes e índices k para os bins discretos usados
[COEFF_BIT_1, K_BIT_1] = precalc_goertzel(FREQ_BIT_1, SAMPLE_RATE, SPS);  % coef p/ 1200Hz
[COEFF_BIT_0, K_BIT_0] = precalc_goertzel(FREQ_BIT_0, SAMPLE_RATE, SPS);  % coef p/ 2200Hz

%% -------------------- Interface: UID do receptor --------------------
MY_UID = input('Digite o UID deste receptor (0-255): ');  % solicita UID
% valida UID (inteiro entre 0 e 255)
if ~(isnumeric(MY_UID) && isscalar(MY_UID) && MY_UID >= 0 && MY_UID <= 255 && floor(MY_UID) == MY_UID)
    error('MY_UID inválido. Insira inteiro entre 0 e 255.');
end
fprintf('[INFO] MY_UID = %d\n', MY_UID);  % exibe UID configurado

% solicita confirmação para iniciar gravação
resp = input('Iniciar gravação? (sim/nao): ', 's');  % prompt textual
if ~strcmpi(resp, 'sim')                              % se não confirmar
    fprintf('Gravação cancelada pelo usuário.\n');   % informa e encerra
    return;                                          % termina execução
end

%% -------------------- Aquisição: gravação (offline) --------------------
recorder = audiorecorder(SAMPLE_RATE, 16, 1);        % cria objeto de gravação (mono, 16 bits)
fprintf('🔴 Gravando... pressione ENTER para parar.\n');  % instrução ao usuário
record(recorder);                                    % inicia gravação
input('Pressione ENTER para PARAR a gravação\n','s'); % bloqueia até ENTER
stop(recorder);                                      % para gravação

audio_signal = getaudiodata(recorder, 'double');     % obtém amostras em double
fprintf('[INFO] Gravação finalizada: %d amostras capturadas.\n', length(audio_signal));  % log

% tenta salvar WAV (opcional, sem interromper fluxo em caso de erro)
try
    audiowrite(OUTPUT_WAV, audio_signal, SAMPLE_RATE);  % escreve arquivo WAV
    fprintf('[INFO] Arquivo WAV salvo: %s\n', OUTPUT_WAV); % confirma salvamento
catch ex
    warning('Falha ao salvar WAV: %s', ex.message);      % avisa se falhar
end

%% -------------------- Visualização inicial --------------------
% mostra forma de onda e FFT para verificar presença dos tons AFSK
Nplot = min(length(audio_signal), 4000);           % número de amostras a exibir
t = (0:Nplot-1) / SAMPLE_RATE;                     % eixo tempo em segundos
figure('Name','Sinal (tempo)','NumberTitle','off'); % cria figura
plot(t, audio_signal(1:Nplot));                     % plota trecho inicial
xlabel('Tempo (s)'); ylabel('Amplitude'); title('Sinal recebido (trecho inicial)'); grid on;

% FFT para diagnóstico (metade positiva)
Nfft = max(2048, 2^nextpow2(length(audio_signal))); % tamanho FFT
F = (0:Nfft-1) * (SAMPLE_RATE / Nfft);             % eixo de frequências
S = abs(fft(audio_signal, Nfft));                  % magnitude da FFT
figure('Name','Espectro (FFT)','NumberTitle','off');
plot(F(1:Nfft/2), S(1:Nfft/2)); hold on;           % plota metade positiva
xline(FREQ_BIT_1, 'r--', '1200 Hz');               % marca 1200 Hz
xline(FREQ_BIT_0, 'b--', '2200 Hz');               % marca 2200 Hz
xlabel('Frequência (Hz)'); ylabel('Magnitude'); title('Espectro do sinal recebido'); grid on;
xlim([0 4000]); hold off;

%% -------------------- Brute-force offsets 0..SPS-1 --------------------
% testa alinhamentos 0..SPS-1; para cada offset calcula mag1/mag0, decide bits,
% executa FSM e valida CRC, aceitando apenas pacotes cujo UIDRX == MY_UID.
num_offsets = SPS;                                  % número de offsets testados
offset_metrics = zeros(num_offsets,1);              % métrica por offset
offset_packet_info = cell(num_offsets,1);           % guarda info por offset
offset_bits = cell(num_offsets,1);                  % bits por offset
offset_mag1 = cell(num_offsets,1);                  % mag@1200 por offset
offset_mag0 = cell(num_offsets,1);                  % mag@2200 por offset
offset_nSymbols = zeros(num_offsets,1);             % nº símbolos por offset

found_for_me = false;                               % flag de sucesso para MY_UID
found_wrong_uid_list = [];                          % lista de UIDs válidos detectados mas não para mim
final_payload = uint8([]);                          % payload final se for para mim
final_header = struct('uid_tx',0,'uid_rx',0,'len',0); % header final se aplicável
best_offset = -1;                                   % offset escolhido (encontrado ou fallback)
best_metric = -Inf;                                 % métrica para fallback

fprintf('\n--- Testando offsets 0..%d ---\n', SPS-1);  % cabeçalho do loop

% loop principal de testes de offsets
for offset = 0:(SPS-1)
    fprintf('Offset %2d: ', offset);               

    % corta trecho a partir do offset; verifica se há dados suficientes
    if (1 + offset) > length(audio_signal)
        fprintf('offset > duração do áudio; pulando\n'); continue;
    end
    seg = audio_signal(1 + offset : end);          % segmento a partir do offset
    nSymbols = floor(length(seg) / SPS);           % quantos símbolos completos cabem
    if nSymbols == 0                                 % se nenhum símbolo completo
        fprintf('áudio muito curto após offset; pulando\n'); continue;
    end

    % trunca segmento para múltiplo de SPS e organiza blocos (cada linha = 1 símbolo)
    seg = seg(1 : nSymbols * SPS);                  % trunca
    blocks = reshape(seg, SPS, nSymbols)';          % matriz [nSymbols x SPS]

    % calcula energia por bloco no bin correspondente via Goertzel (vetorizado)
    mag1 = goertzel_mag_vectorized(blocks, COEFF_BIT_1); % energia por símbolo @1200Hz
    mag0 = goertzel_mag_vectorized(blocks, COEFF_BIT_0); % energia por símbolo @2200Hz

    % decisão de bits por símbolo (1 se mag1 > mag0)
    bits = (mag1 > mag0);                           % vetor lógico de bits por símbolo

    % métrica diagnóstica: soma das diferenças (quanto mais alto, melhor separação)
    metric = sum(abs(mag1 - mag0));                 % métrica simples por offset
    offset_metrics(offset+1) = metric;              % armazena métrica
    offset_bits{offset+1} = bits;                   % armazena bits
    offset_mag1{offset+1} = mag1;                   % armazena mag1
    offset_mag0{offset+1} = mag0;                   % armazena mag0
    offset_nSymbols(offset+1) = nSymbols;           % armazena nº símbolos

    % executa FSM (procura SYNC, lê header/payload/CRC) sobre bits
    [packet_found, header, payload, pos_struct] = fsm_decode_stream(bits, SYNC_WORD_VAL, ...
        STATE_SEARCHING_SYNC, STATE_READING_HEADER, STATE_READING_PAYLOAD, STATE_READING_CRC, STATE_VALIDATING);

    % armazena informação do offset para relatório
    offset_packet_info{offset+1} = struct('packet_found', packet_found, 'header', header, 'payload', payload, 'pos', pos_struct);

    % relatório detalhado por offset
    if packet_found                                    % se FSM encontrou pacote com CRC válido
        if isfield(header,'uid_rx')                     % se header tem uid_rx
            fprintf('pacote válido detectado (UIDRX=%d, UIDTX=%d, LEN=%d)\n', header.uid_rx, header.uid_tx, header.len);
        else
            fprintf('pacote válido detectado (header incompleto)\n');
        end

        % aceita apenas se o pacote for destinado a este id (MY_UID)
        if isfield(header,'uid_rx') && header.uid_rx == MY_UID
            found_for_me = true;                       % marca sucesso
            final_payload = payload;                   % salva payload
            final_header = header;                     % salva header
            best_offset = offset;                      % offset selecionado
            best_metric = metric;                      % métrica associada
            break;                                     % interrompe busca
        else
            % pacote válido mas para outro UID -> registra e continua
            fprintf('   (válido, porém destinado a UID %d)\n', header.uid_rx);
            found_wrong_uid_list = [found_wrong_uid_list, header.uid_rx]; %#ok<AGROW>
        end
    else
        fprintf('sem pacote válido (metric=%.2f)\n', metric); % sem pacote válido neste offset
    end

    % atualiza fallback por métrica caso nenhum pacote direto seja encontrado
    if metric > best_metric
        best_metric = metric; best_offset = offset;
    end
end

% informa offset final escolhido (encontrado ou por fallback)
fprintf('[INFO] Best offset final = %d\n', best_offset);

%% -------------------- Resultado final e relatório --------------------
% Se pacote destinado a MY_UID foi encontrado, apresenta a mensagem
if found_for_me
    fprintf('\n--- PACOTE DESTINADO A ESTE RECEPTOR ---\n');   % cabeçalho
    fprintf('UID_TX: %d\n', final_header.uid_tx);           % remetente
    fprintf('UID_RX: %d (este receptor)\n', final_header.uid_rx); % receptor
    fprintf('Tamanho payload: %d bytes\n', final_header.len); % tamanho
    try
        fprintf('Payload (ASCII): %s\n', char(final_payload)); % imprime payload como ASCII
    catch
        fprintf('Payload (bytes): %s\n', mat2str(final_payload)); % fallback imprime bytes
    end
    fprintf('Offset utilizado: %d\n', best_offset);         % offset efetivo
else
    % se encontrou pacotes válidos para outros UIDs, lista-os
    if ~isempty(found_wrong_uid_list)
        fprintf('\n--- PACOTES VÁLIDOS PARA OUTROS UIDS ---\n');
        fprintf('UIDs encontrados: %s\n', num2str(unique(found_wrong_uid_list))); % lista UIDs únicos
        fprintf('Nenhum pacote destinado ao UID %d foi encontrado.\n', MY_UID);
    else
        % nenhum pacote válido detectado em nenhum offset
        fprintf('\n--- NENHUM PACOTE VÁLIDO DETECTADO ---\n');
        fprintf('Possíveis causas: sinal fraco, ruído, TX não transmitiu ou desalinhamento severo.\n');
    end
end

%% -------------------- Preparação para plots finais --------------------
% seleciona dados do best_offset para visualização
idx_best = best_offset + 1;                       % index 1-based
if idx_best >= 1 && idx_best <= num_offsets && ~isempty(offset_bits{idx_best})
    best_bits = offset_bits{idx_best};            % bits recuperados no best offset
    best_mag1 = offset_mag1{idx_best};            % mag@1200 no best offset
    best_mag0 = offset_mag0{idx_best};            % mag@2200 no best offset
    best_nSymbols = offset_nSymbols(idx_best);    % nº de símbolos
else
    best_bits = []; best_mag1 = []; best_mag0 = []; best_nSymbols = 0; % vazio se não disponível
end

%% -------------------- Plot final: Energia por símbolo (Goertzel) --------------------
figure('Name','Energia por símbolo (Goertzel)','NumberTitle','off'); % cria figura
if ~isempty(best_mag1) && ~isempty(best_mag0)            % garante dados
    plot(1:best_nSymbols, best_mag1, '-r', 'DisplayName', sprintf('mag %d Hz', FREQ_BIT_1)); hold on; % mag 1200Hz
    plot(1:best_nSymbols, best_mag0, '-b', 'DisplayName', sprintf('mag %d Hz', FREQ_BIT_0));            % mag 2200Hz
    xlabel('Índice do símbolo'); ylabel('Energia (relativa)'); title(sprintf('Energia por símbolo (offset = %d)', best_offset));
    legend('Location','best'); grid on; hold off;
else
    text(0.1,0.5,'Sem dados Goertzel para o offset escolhido','FontSize',10); axis off;
end

%% -------------------- Plot final: Bits reconstruídos --------------------
figure('Name','Bits reconstruídos (limpo)','NumberTitle','off'); % cria figura
if ~isempty(best_bits)
    stairs(1:length(best_bits), double(best_bits), 'LineWidth', 1.8); hold on; % degrau representando níveis 0/1
    plot(1:length(best_bits), double(best_bits), 'ko', 'MarkerSize', 4, 'MarkerFaceColor', 'k'); % marcadores discretos
    ylim([-0.3 1.3]); yticks([0 1]); yticklabels({'0','1'}); xlabel('Índice do símbolo'); ylabel('Bit');
    title(sprintf('Bits reconstruídos (offset = %d)', best_offset)); grid on; hold off;
else
    text(0.2,0.5,'Nenhum bit disponível para exibição','FontSize',10); axis off;
end

%% -------------------- Funções auxiliares --------------------

% precalc_goertzel: calcula índice k e coeficiente para Goertzel
function [coef, k] = precalc_goertzel(freq, fs, N)
    % freq: frequência alvo (Hz)
    % fs: taxa de amostragem (Hz)
    % N: tamanho do bloco (amostras por símbolo)
    k_float = (N * freq) / fs;    % índice real do bin DFT correspondente
    k = round(k_float);           % arredonda para o bin inteiro mais próximo
    coef = 2.0 * cos(2.0 * pi * k / N);  % coeficiente recursivo usado no Goertzel
end

% goertzel_mag_vectorized: aplica Goertzel a cada linha de 'samples'
function mag_sq = goertzel_mag_vectorized(samples, coef)
    % samples: matriz [num_blocks x N], cada linha é um bloco de N=SPS amostras
    % coef: coeficiente retornado por precalc_goertzel
    [num_blocks, N] = size(samples);   % número de blocos e tamanho do bloco
    q1 = zeros(num_blocks,1);          % estado q1 inicial por bloco
    q2 = zeros(num_blocks,1);          % estado q2 inicial por bloco
    for n = 1:N                         % itera sobre amostras do bloco
        q0 = coef .* q1 - q2 + samples(:, n); % recursão vetorial
        q2 = q1; q1 = q0;               % atualiza estados
    end
    % magnitude ao quadrado proporcional à energia no bin
    mag_sq = (q1.^2) + (q2.^2) - (coef .* q1 .* q2);
end

% fsm_decode_stream: percorre vetor de bits e tenta extrair pacotes válidos
function [packet_found, header, payload, pos_struct] = fsm_decode_stream(bits_out, SYNC_WORD_VAL, STATE_SEARCHING_SYNC, STATE_READING_HEADER, STATE_READING_PAYLOAD, STATE_READING_CRC, STATE_VALIDATING)
    % inicializa variáveis de saída
    packet_found = false;                                   % flag de sucesso
    header = struct('uid_tx',0,'uid_rx',0,'len',0);         % header padrão
    payload = uint8([]);                                    % payload padrão
    pos_struct = struct('sync_ends',[],'header_start',[],'payload_start',[],'crc_start',[]); % marcadores

    % inicializa estado e buffers locais
    state = STATE_SEARCHING_SYNC;                           % estado inicial
    bit_buffer = [];                                        % buffer de bits (para formar bytes)
    sync_search_buffer = zeros(1,16);                       % janela de 16 bits para detectar SYNC
    byte_buffer = uint8([]);                                % acumula header+payload para CRC
    header_tmp = struct(); payload_tmp = uint8([]); received_crc = uint8([]); header_len_remaining = 3; payload_len_remaining = 0; crc_len_remaining = 2;

    % percorre todos os bits do vetor de entrada
    for i = 1:length(bits_out)
        bit = bits_out(i);                                  % lê bit atual
        switch state
            case STATE_SEARCHING_SYNC
                % desloca janela de 16 bits (MSB-first)
                sync_search_buffer = [sync_search_buffer(2:end), bit];
                % converte janela em inteiro
                current_word = 0;
                for b = 1:16
                    current_word = current_word * 2 + sync_search_buffer(b);
                end
                % se igual ao SYNC, prepara leitura de header
                if current_word == SYNC_WORD_VAL
                    pos_struct.sync_ends = [pos_struct.sync_ends, i];  % registra fim do SYNC
                    pos_struct.header_start = i + 1;                 % início do header
                    bit_buffer = []; byte_buffer = uint8([]); header_len_remaining = 3; payload_tmp = uint8([]); received_crc = uint8([]); payload_len_remaining = 0; crc_len_remaining = 2;
                    state = STATE_READING_HEADER;                     % altera estado
                end

            case {STATE_READING_HEADER, STATE_READING_PAYLOAD, STATE_READING_CRC}
                % acumula bit no buffer de bits
                bit_buffer = [bit_buffer, bit];
                % quando completamos 8 bits, converte em byte
                if length(bit_buffer) == 8
                    byte_val = uint8(0);
                    for bb = 1:8
                        byte_val = bitshift(byte_val, 1) + uint8(bit_buffer(bb)); % MSB-first
                    end
                    bit_buffer = [];  % limpa buffer de bits
                    % processa byte de acordo com o estado atual
                    [state, byte_buffer, header_tmp, payload_tmp, received_crc, payload_len_remaining, header_len_remaining, crc_len_remaining, packet_success, packet_reject] = ...
                        process_byte(byte_val, state, byte_buffer, header_tmp, payload_tmp, received_crc, payload_len_remaining, header_len_remaining, crc_len_remaining, STATE_READING_HEADER, STATE_READING_PAYLOAD, STATE_READING_CRC, STATE_VALIDATING, STATE_SEARCHING_SYNC);
                    % marca posição do payload se entramos na leitura do CRC
                    if state == STATE_READING_CRC && isempty(pos_struct.payload_start)
                        pos_struct.payload_start = pos_struct.header_start + 24; % header = 3 bytes = 24 símbolos
                    end
                    % se pacote validado com sucesso, preenche campos de saída e retorna
                    if packet_success
                        packet_found = true;
                        header.uid_tx = header_tmp.uid_tx; header.uid_rx = header_tmp.uid_rx; header.len = header_tmp.len;
                        payload = payload_tmp;
                        pos_struct.crc_start = pos_struct.payload_start + header_tmp.len * 8;
                        return;
                    end
                    % se CRC inválido, volta a procurar SYNC
                    if packet_reject
                        state = STATE_SEARCHING_SYNC; sync_search_buffer = zeros(1,16); bit_buffer = []; byte_buffer = uint8([]); header_tmp = struct(); payload_tmp = uint8([]); received_crc = uint8([]); header_len_remaining = 3; crc_len_remaining = 2; payload_len_remaining = 0;
                    end
                end
        end
    end
end

% process_byte: processa um byte conforme o estado (header/payload/crc)
function [state_out, byte_buffer_out, header_out, payload_out, received_crc_out, payload_len_out, header_len_out, crc_len_out, packet_success, packet_reject] = ...
        process_byte(byte_val, state_in, byte_buffer_in, header_in, payload_in, received_crc_in, payload_len_in, header_len_in, crc_len_in, STATE_READING_HEADER, STATE_READING_PAYLOAD, STATE_READING_CRC, STATE_VALIDATING, STATE_SEARCHING_SYNC)
    % inicializa saídas com valores de entrada
    state_out = state_in; byte_buffer_out = byte_buffer_in; header_out = header_in; payload_out = payload_in; received_crc_out = received_crc_in; payload_len_out = payload_len_in; header_len_out = header_len_in; crc_len_out = crc_len_in; packet_success = false; packet_reject = false;
    % processa conforme estado atual
    switch state_in
        case STATE_READING_HEADER
            byte_buffer_out = [byte_buffer_in, byte_val];    % acumula byte do header
            header_len_out = header_len_in - 1;              % decrementa contador do header
            if header_len_out == 0                             % quando header completo
                header_out.uid_tx = byte_buffer_out(1);       % extrai UID TX
                header_out.uid_rx = byte_buffer_out(2);       % extrai UID RX
                header_out.len    = byte_buffer_out(3);       % extrai LEN
                payload_len_out = double(header_out.len);     % define contador do payload
                state_out = STATE_READING_PAYLOAD;            % passa a ler payload
                byte_buffer_out = [];                         % limpa byte_buffer temporário
            end

        case STATE_READING_PAYLOAD
            payload_out = [payload_in, byte_val];              % acumula byte do payload
            payload_len_out = payload_len_in - 1;              % decrementa contador
            if payload_len_out == 0                            % se payload completo
                state_out = STATE_READING_CRC;                 % passa a ler CRC
                byte_buffer_out = uint8([header_out.uid_tx, header_out.uid_rx, header_out.len, payload_out]); % prepara dados para CRC
            end

        case STATE_READING_CRC
            received_crc_out = [received_crc_in, byte_val];    % acumula byte do CRC
            crc_len_out = crc_len_in - 1;                      % decrementa contador de CRC
            if crc_len_out == 0                                % CRC lido completamente
                state_out = STATE_VALIDATING;                  % vai validar
                packet_success = validate_packet(byte_buffer_out, received_crc_out); % valida CRC calculando sobre header+payload
                if ~packet_success
                    packet_reject = true;                     % marca rejeição se CRC inválido
                end
            end
    end
end

% validate_packet: calcula CRC-16 CCITT e compara com bytes recebidos
function ok = validate_packet(data_to_check, received_crc)
    calc_crc_val = crc16_ccitt(data_to_check);                  % calcula CRC como uint16
    calc_crc_bytes = typecast(swapbytes(uint16(calc_crc_val)), 'uint8'); % converte para bytes big-endian
    ok = isequal(calc_crc_bytes, received_crc);                 % compara vetores
end

% crc16_ccitt: implementação padrão CRC-16 CCITT (poly 0x1021, seed 0xFFFF)
function crc = crc16_ccitt(data)
    crc = uint16(hex2dec('FFFF')); poly = uint16(hex2dec('1021')); % inicializa
    for i = 1:length(data)                                        % percorre bytes
        byte = uint16(data(i));                                   % pega byte atual
        crc = bitxor(crc, bitshift(byte, 8));                     % XOR com byte na posição alta
        for j = 1:8                                               % processa cada bit
            if bitand(crc, hex2dec('8000'))                       % se MSB = 1
                crc = bitxor(bitshift(crc, 1), poly);             % shift + XOR polinômio
            else
                crc = bitshift(crc, 1);                           % apenas shift
            end
        end
    end
    crc = bitand(crc, hex2dec('FFFF'));                           % assegura 16 bits
end

