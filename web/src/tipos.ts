export type Papel = "admin" | "colaborador" | "leitor";

export interface Usuario {
  id: number; email: string; nome: string; papel: Papel; instituicao: string | null;
  ativo: boolean; ultimo_login: string | null; criado_em: string | null;
}

export interface Empresa {
  id: number; nome: string; cidade: string | null; segmento: string | null; observacoes: string | null;
  n_coletas: number; n_ensaios: number;
}

export type Tipo = "branco" | "rna";
export const NOME_TIPO: Record<Tipo, string> = { branco: "Branco", rna: "RNA" };

/** Uma linha da base: um voltamograma DPV de branco ou de RNA, com o pico. */
export interface Ensaio {
  id: number; arquivo: string | null; empresa_id: number | null; coleta_id: number | null; eletrodo_id: string;
  canal: string | null; elemento_captura: string | null; tipo: Tipo; bacteria: string | null; concentracao: number;
  e_pico_v: number | null; i_pico_ua: number | null; altura_ua: number | null; branco_id: number | null;
  queda_pct: number | null; abaixo_do_branco: boolean | null; qc_flag: "PASS" | "FAIL" | null;
  medido_em: string | null; observacoes: string | null;
}

export interface EnsaioDetalhe extends Ensaio {
  potential_v: number[]; current_ua: number[]; procedimento: string | null; tecnica: string;
  tipo_eletrodo: string | null; tratamento: string | null; i_base_ua: number | null; largura_v: number | null;
  area_uav: number | null; criado_em: string;
  branco: { id: number; arquivo: string | null; altura_ua: number | null; potential_v: number[]; current_ua: number[] } | null;
}

export interface Calibracao {
  n: number; inclinacao_pct_por_decada: number; intercepto_pct: number; r2: number;
  lod_ng_ml: number | null; lod_motivo?: string;
}

export interface Coleta {
  id: number; empresa_id: number | null; empresa: string | null; descricao: string | null; data_coleta: string | null;
  n_ensaios: number; n_branco: number; n_rna: number; avisos: string[]; origem: string | null;
  criado_por: string | null; criado_em: string; ensaios?: Ensaio[];
  importacao?: { lidos: number; gravados: number; ja_no_banco: number; nao_gravados: number; ligados_ao_branco: number; avisos: string[] };
}

export const NOME_PAPEL: Record<Papel, string> = { admin: "Administrador", colaborador: "Colaborador", leitor: "Leitor" };

export interface Metricas {
  n?: number; balanced_accuracy: number | null; roc_auc: number | null; sensibilidade: number | null;
  especificidade: number | null; acuracia?: number; matriz_confusao?: number[][];
}

export interface LinhaPlacar {
  posicao: number; representacao: string; algoritmo: string; balanced_accuracy: number | null; roc_auc: number | null;
  sensibilidade: number | null; especificidade: number | null; erro: string | null;
}

/** Cartão do modelo (o mesmo que fica em modelos/<id>/cartao.json). */
export interface Modelo {
  id: string; criado_em: string; algoritmo: string; algoritmo_nome: string; representacao: string;
  representacao_nome: string; grade: { inicio_v: number; fim_v: number; pontos: number };
  dados: { n_ensaios: number; n_branco: number; n_rna: number; n_eletrodos: number; n_treino: number; n_teste: number;
           eletrodos_teste: string[]; concentracoes_ng_ml: number[] };
  validacao: string; metricas_cv: Metricas; metricas_teste: Metricas | null; referencia: string;
  ab_referencia: number; confiavel: boolean; avisos: string[]; placar: LinhaPlacar[]; em_uso?: boolean; seed: number;
}

export interface InfoAlgoritmo {
  id: string; nome: string; ajuste: string; familia: string; o_que: string; parametros?: string; descricao: string;
}
export interface InfoVariante { id: string; nome: string; o_que: string; descricao: string }
export interface Catalogo { algoritmos: InfoAlgoritmo[]; variantes: InfoVariante[]; ba_confiavel: number }

export interface Treino {
  id: string; estado: "na fila" | "rodando" | "concluido" | "erro" | "interrompido"; progresso: number; etapa: string;
  params: { algoritmos: string[]; variantes: string[]; empresas: number[]; ativar: boolean };
  usuario: string; criado_em: string; terminado_em?: string; mensagem: string; modelo: string | null;
}

export interface ResultadoPrevisao {
  arquivo: string; sha256?: string; eletrodo_id?: string | null; tipo_informado?: Tipo | null;
  concentracao_informada?: number | null; resultado: string; prob_contaminado: number | null; motivo: string | null;
  e_pico_v?: number | null; i_pico_ua?: number | null; altura_ua?: number | null; largura_v?: number | null;
  potential_v?: number[]; current_ua?: number[];
}
