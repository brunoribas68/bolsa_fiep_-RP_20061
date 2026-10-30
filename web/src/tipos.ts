export type Papel = "admin" | "colaborador" | "leitor";

export interface Usuario {
  id: number; email: string; nome: string; papel: Papel; instituicao: string | null;
  ativo: boolean; ultimo_login: string | null; criado_em: string | null;
}

export interface Empresa {
  id: number; nome: string; cidade: string | null; segmento: string | null; observacoes: string | null;
  n_coletas: number; n_amostras: number;
}

export interface Coleta {
  id: number; empresa_id: number | null; empresa: string | null; descricao: string | null;
  data_coleta: string | null; conjunto: string | null; n_amostras: number; n_medicoes: number;
  amostras_sem_rotulo: number; avisos: string[]; origem: string | null; criado_por: string | null; criado_em: string;
  arquivos?: { arquivo: string; papel: string; tamanho_bytes: number | null; sha256: string }[];
  replicas?: { sample_id: string; replicate_id: string; n_medicoes: number; estagios: string; n_aprovadas: number }[];
}

export interface AmostraLinha {
  sample_id: string; empresa_id: number | null; empresa: string | null; coleta_id: number | null;
  contamination_status: number | null; sample_log10_mean_cfu_ml: number | null; target_bacterium: string | null;
  surface_type: string | null; conjunto: string | null; n_replicas: number; n_completas: number;
  n_medicoes: number; ultima_previsao: string | null;
}

export interface Medicao {
  measurement_id: string; replicate_id: string | null; sensor_state: string | null; tecnica: string | null;
  fonte: string | null; arquivo_origem: string | null; measurement_date: string | null; qc_planilha: string | null;
  qc_auto: string | null; qc_final: string | null; qc_motivos: string | null; n_pontos: number | null;
}

export interface AmostraDetalhe {
  sample_id: string; empresa_id: number | null; empresa: string | null; coleta_id: number | null;
  contamination_status: number | null; sample_log10_mean_cfu_ml: number | null; target_bacterium: string | null;
  surface_type: string | null; conjunto: string | null; observacoes: string | null; atualizado_em: string | null;
  atualizado_por: string | null; medicoes: Medicao[];
  plaqueamentos: { replica: number; colonias: number | null; ufc_ml: number | null; log10_ufc_ml: number | null }[];
  previsoes: { previsto_em: string; modelo_id: string; replica: string | null; status: string; resultado: string;
               prob_contaminada: number | null; log10_ufc_ml_estimado: number | null; nivel: string | null;
               motivo: string | null }[];
}

export interface Curva {
  measurement_id: string; replicate_id: string | null; sensor_state: string | null; tecnica: string | null;
  qc_final: string | null; potential_v: number[]; current_ua: number[];
}

export interface PrevisaoAmostra {
  sample_id: string; resultado: string; prob_contaminada: number | null; replicas_avaliadas: number;
  replicas_total: number; concordancia: number | null; log10_ufc_ml_estimado: number | null;
  nivel_contaminacao: string; rotulo_informado: number | null; base?: string;
}

export interface PrevisaoReplica {
  sample_id: string | null; replicate_id: string | null; measurement_id: string | null; status: string;
  resultado: string; prob_contaminada: number | null; log10_ufc_ml_estimado: number | null;
  nivel_contaminacao?: string; motivo: string | null; base?: string | null;
}

/** Picos de uma medição: DPV/SWV (e_pico...) ou CV (epa, epc...). */
export interface Pico {
  measurement_id: string; sample_id: string | null; replicate_id: string | null; sensor_state: string | null;
  etapa?: string | null; tecnica: string | null; arquivo: string | null;
  e_pico_v?: number | null; i_pico_ua?: number | null; i_base_ua?: number | null; altura_ua?: number | null;
  largura_v?: number | null; epa_v?: number | null; ipa_ua?: number | null; epc_v?: number | null; ipc_ua?: number | null;
  delta_ep_v?: number | null; e_meia_v?: number | null; razao_ipa_ipc?: number | null; ciclos?: number | null;
}

export const ESTAGIOS = ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"] as const;
export const NOME_ESTAGIO: Record<string, string> = {
  carbon_clean: "Carbono limpo", capture_probe: "Sonda de captura", capture_probe_16S_rRNA: "Sonda + rRNA 16S",
  bloqueio: "Bloqueio", mAb_NS1: "mAb-NS1", final: "Final",
};

export interface Protocolo { nome: string; tecnica: string; estagios: { id: string; nome: string }[] }
export const NOME_CONJUNTO: Record<string, string> = {
  "": "Sorteio (50/25/25)", treino: "Treino", validacao: "Validação", teste: "Teste",
};
export const NOME_PAPEL: Record<Papel, string> = { admin: "Administrador", colaborador: "Colaborador", leitor: "Leitor" };

export interface ModeloResumo {
  id: string; criado_em: string | null; modelo: string | null; variante: string | null; protocolo: string | null;
  experimento: string | null; n_amostras: number | null; limiar: number | null; em_uso: boolean;
  teste_acuracia: number | null; teste_balanced_accuracy: number | null; teste_sensibilidade: number | null;
  teste_especificidade: number | null; teste_roc_auc: number | null; teste_amostra_balanced_accuracy: number | null;
  validacao_balanced_accuracy: number | null; cv_balanced_accuracy: number | null; regressor: string | null;
}

export interface LinhaComparacao {
  posicao: number; variante: string; modelo: string; cv_balanced_accuracy: number | null; cv_ba_desvio: number | null;
  val_balanced_accuracy: number | null; val_roc_auc: number | null; teste_balanced_accuracy: number | null;
  teste_sensibilidade: number | null; teste_especificidade: number | null; teste_roc_auc: number | null;
}

export interface ModeloDetalhe extends ModeloResumo {
  cartao: Record<string, unknown>;
  resumo: { teste?: string; amostras_treino?: number; amostras_validacao?: number; amostras_teste?: number;
            formula_sisso?: string | null; criterio_escolha?: string; estagios?: string[]; tecnica?: string;
            melhor_regressao?: Record<string, number | string> | null; teste_niveis?: { acuracia: number } | null };
  comparacao: LinhaComparacao[];
  regressao: { variante: string; modelo: string; cv_rmse: number | null; val_rmse: number | null; teste_rmse: number | null; teste_r2: number | null }[];
  figuras: { arquivo: string; titulo: string }[];
}

export interface InfoAlgoritmo {
  id: string; nome: string; ajuste: string; familia?: string; o_que: string; parametros?: string; descricao: string;
}
export interface InfoVariante { id: string; nome: string; o_que: string; descricao: string }
export interface Catalogo {
  algoritmos: (InfoAlgoritmo & { familia: string })[];
  variantes: InfoVariante[];
  regressores?: InfoAlgoritmo[];
}

export interface Treino {
  id: string; estado: "na fila" | "rodando" | "concluido" | "erro" | "interrompido"; progresso: number; etapa: string;
  params: { algoritmos: string[]; variantes: string[]; empresas: number[]; com_exemplo: boolean; ativar: boolean };
  usuario: string; criado_em: string; terminado_em?: string; mensagem: string; modelo: string | null; divisao?: string;
}
