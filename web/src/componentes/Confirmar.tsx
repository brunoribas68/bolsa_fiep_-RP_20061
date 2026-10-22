import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from "@mui/material";
import type { ReactNode } from "react";

export default function Confirmar({ aberto, titulo, texto, acao = "Confirmar", perigo, aoFechar, aoConfirmar }: {
  aberto: boolean; titulo: string; texto: ReactNode; acao?: string; perigo?: boolean;
  aoFechar: () => void; aoConfirmar: () => void;
}) {
  return (
    <Dialog open={aberto} onClose={aoFechar} maxWidth="xs" fullWidth>
      <DialogTitle>{titulo}</DialogTitle>
      <DialogContent><DialogContentText>{texto}</DialogContentText></DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={aoFechar}>Cancelar</Button>
        <Button variant="contained" color={perigo ? "error" : "primary"} onClick={aoConfirmar}>{acao}</Button>
      </DialogActions>
    </Dialog>
  );
}
