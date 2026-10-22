import { createTheme, type PaletteMode } from "@mui/material/styles";

// Paleta das séries (validada para daltonismo): mesma ordem no app inteiro
export const SERIES = { light: ["#2a78d6", "#eb6834", "#1baf7a"], dark: ["#4a90e2", "#f08257", "#2fc48f"] };

export function criarTema(modo: PaletteMode) {
  const claro = modo === "light";
  return createTheme({
    palette: {
      mode: modo,
      primary: { main: claro ? "#1f5fae" : "#5b9be6" },
      secondary: { main: claro ? "#eb6834" : "#f08257" },
      error: { main: claro ? "#b4382b" : "#f08a7e" },
      success: { main: claro ? "#13744f" : "#5fd3a4" },
      warning: { main: claro ? "#a86a00" : "#f2c46b" },
      background: { default: claro ? "#f4f6f9" : "#0f141a", paper: claro ? "#ffffff" : "#161c24" },
      divider: claro ? "#e3e6eb" : "#273040",
      text: { primary: claro ? "#18202b" : "#e8ecf1", secondary: claro ? "#5b6472" : "#9aa5b4" },
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      h4: { fontWeight: 700, fontSize: "1.55rem", letterSpacing: "-0.01em" },
      h6: { fontWeight: 650, fontSize: "1rem" },
      subtitle2: { fontWeight: 650 },
      button: { textTransform: "none", fontWeight: 600 },
      overline: { fontWeight: 600, letterSpacing: "0.06em" },
    },
    components: {
      MuiCard: { defaultProps: { variant: "outlined" } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
      MuiSelect: { defaultProps: { size: "small", displayEmpty: true } },
      // rótulo sempre no alto: selects com opção vazia ("Todos", "Sem resultado") não ficam parecendo vazios
      MuiInputLabel: { defaultProps: { shrink: true } },
      MuiOutlinedInput: { defaultProps: { notched: true } },
      MuiTableCell: {
        styleOverrides: {
          head: { fontWeight: 600, fontSize: 12, textTransform: "uppercase", letterSpacing: ".04em",
                  color: claro ? "#5b6472" : "#9aa5b4", whiteSpace: "nowrap" },
        },
      },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiAppBar: { defaultProps: { elevation: 0, color: "inherit" } },
    },
  });
}
