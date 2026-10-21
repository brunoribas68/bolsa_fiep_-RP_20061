import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { num } from "../formato";
import { NOME_CONJUNTO, type AmostraLinha } from "../tipos";
import { ChipResultado, ChipRotulo } from "./rotulos";

function CelulaRotulo({ a, aoMudar }: { a: AmostraLinha; aoMudar: (n: AmostraLinha) => void }) {
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  async function salvar(campos: Partial<AmostraLinha>) {
    setSalvando(true); setErro("");
    try {
      await api.patch(`/api/amostras/${encodeURIComponent(a.sample_id)}`, campos);
      aoMudar({ ...a, ...campos });
    } catch (e) { setErro((e as Error).message); } finally { setSalvando(false); }
  }
  return (
    <>
      <td>
        <select aria-label={`Resultado de ${a.sample_id}`} disabled={salvando}
                value={a.contamination_status === null ? "" : String(a.contamination_status)}
                onChange={e => salvar({ contamination_status: e.target.value === "" ? null : Number(e.target.value) })}>
          <option value="">Sem resultado</option><option value="1">Contaminada</option><option value="0">Não contaminada</option>
        </select>
        {erro && <div className="erro pequeno">{erro}</div>}
      </td>
      <td className="num">
        <input aria-label={`Carga de ${a.sample_id}`} style={{ width: 80, textAlign: "right" }} inputMode="decimal"
               defaultValue={a.sample_log10_mean_cfu_ml ?? ""} disabled={salvando}
               onBlur={e => {
                 const v = e.target.value.trim().replace(",", ".");
                 const novo = v === "" ? null : Number(v);
                 if (novo !== a.sample_log10_mean_cfu_ml && (novo === null || !Number.isNaN(novo)))
                   salvar({ sample_log10_mean_cfu_ml: novo });
               }} />
      </td>
    </>
  );
}

export default function TabelaAmostras({ itens, aoMudar, mostrarEmpresa = true }: {
  itens: AmostraLinha[]; aoMudar: (a: AmostraLinha) => void; mostrarEmpresa?: boolean;
}) {
  const { pode } = useAuth();
  const editar = pode("editar");
  return (
    <div className="tabela">
      <table>
        <thead><tr>
          <th>Amostra</th>{mostrarEmpresa && <th>Empresa</th>}
          <th>Plaqueamento</th><th className="num">Carga (log₁₀ UFC/mL)</th>
          <th className="num">Réplicas completas</th><th>Uso</th><th>Última previsão</th>
        </tr></thead>
        <tbody>
          {itens.map(a => (
            <tr key={a.sample_id}>
              <td><Link to={`/amostras/${encodeURIComponent(a.sample_id)}`} className="mono">{a.sample_id}</Link></td>
              {mostrarEmpresa && <td>{a.empresa || <span className="mudo">—</span>}</td>}
              {editar ? <CelulaRotulo a={a} aoMudar={aoMudar} /> : (
                <><td><ChipRotulo v={a.contamination_status} /></td><td className="num">{num(a.sample_log10_mean_cfu_ml, 1)}</td></>
              )}
              <td className="num">
                <span className={a.n_completas ? "" : "chip rep"}>{a.n_completas} de {a.n_replicas}</span>
              </td>
              <td>{NOME_CONJUNTO[a.conjunto || ""].replace(" (50/25/25)", "")}</td>
              <td><ChipResultado r={a.ultima_previsao} /></td>
            </tr>
          ))}
          {!itens.length && <tr><td colSpan={7} className="vazio">Nenhuma amostra.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
