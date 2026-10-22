import BusinessOutlined from "@mui/icons-material/BusinessOutlined";
import CloudUploadOutlined from "@mui/icons-material/CloudUploadOutlined";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import GroupOutlined from "@mui/icons-material/GroupOutlined";
import Logout from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import PersonOutline from "@mui/icons-material/PersonOutline";
import ScienceOutlined from "@mui/icons-material/ScienceOutlined";
import ShowChart from "@mui/icons-material/ShowChart";
import {
  AppBar, Avatar, Box, CircularProgress, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon,
  ListItemText, Stack, Toolbar, Tooltip, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import { useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Amostras from "./paginas/Amostras";
import AmostraDetalhe from "./paginas/AmostraDetalhe";
import ColetaDetalhe from "./paginas/ColetaDetalhe";
import Coletas from "./paginas/Coletas";
import Conta from "./paginas/Conta";
import Empresas from "./paginas/Empresas";
import Login from "./paginas/Login";
import NovaColeta from "./paginas/NovaColeta";
import Painel from "./paginas/Painel";
import Prever from "./paginas/Prever";
import Usuarios from "./paginas/Usuarios";
import { NOME_PAPEL } from "./tipos";

const LARGURA = 248;

export function Marca({ tamanho = 34 }: { tamanho?: number }) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path d="M5 20c4 0 5-9 9-9s4 11 8 11 4-6 5-6" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function Menu({ aoNavegar }: { aoNavegar?: () => void }) {
  const { usuario, sair, pode } = useAuth();
  const { pathname } = useLocation();
  const itens = [
    { para: "/", nome: "Painel", Ic: DashboardOutlined },
    { para: "/coletas", nome: "Coletas", Ic: CloudUploadOutlined },
    { para: "/amostras", nome: "Amostras", Ic: ScienceOutlined },
    { para: "/prever", nome: "Previsão rápida", Ic: ShowChart },
    { para: "/empresas", nome: "Empresas", Ic: BusinessOutlined },
    ...(pode("admin") ? [{ para: "/usuarios", nome: "Usuários", Ic: GroupOutlined }] : []),
  ];
  const ativo = (para: string) => (para === "/" ? pathname === "/" : pathname.startsWith(para));
  return (
    <Stack sx={{ height: "100%" }}>
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ px: 2.5, py: 2.25, color: "primary.main" }}>
        <Marca />
        <Box sx={{ color: "text.primary" }}>
          <Typography fontWeight={700} lineHeight={1.2}>FIEP</Typography>
          <Typography variant="caption" color="text.secondary">Voltametria · contaminação</Typography>
        </Box>
      </Stack>
      <List sx={{ px: 1.5, flex: 1 }}>
        {itens.map(({ para, nome, Ic }) => (
          <ListItemButton key={para} component={Link} to={para} selected={ativo(para)} onClick={aoNavegar}
                          sx={{ borderRadius: 2, mb: .5, "&.Mui-selected": { color: "primary.main" } }}>
            <ListItemIcon sx={{ minWidth: 36, color: "inherit" }}><Ic fontSize="small" /></ListItemIcon>
            <ListItemText primary={nome} primaryTypographyProps={{ fontWeight: 550, fontSize: 14.5 }} />
          </ListItemButton>
        ))}
      </List>
      <Divider />
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ p: 2 }}>
        <Avatar sx={{ width: 34, height: 34, bgcolor: "primary.main", fontSize: 14 }}>
          {usuario?.nome.split(" ").map(p => p[0]).slice(0, 2).join("")}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{usuario?.nome}</Typography>
          <Typography variant="caption" color="text.secondary">{usuario && NOME_PAPEL[usuario.papel]}</Typography>
        </Box>
        <Tooltip title="Minha conta"><IconButton component={Link} to="/conta" size="small" onClick={aoNavegar}><PersonOutline fontSize="small" /></IconButton></Tooltip>
        <Tooltip title="Sair"><IconButton size="small" onClick={sair}><Logout fontSize="small" /></IconButton></Tooltip>
      </Stack>
    </Stack>
  );
}

export default function App() {
  const { usuario, carregando, pode } = useAuth();
  const local = useLocation();
  const tema = useTheme();
  const largo = useMediaQuery(tema.breakpoints.up("md"));
  const [aberto, setAberto] = useState(false);

  if (carregando) return <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}><CircularProgress /></Box>;
  if (!usuario) {
    return (
      <Routes>
        <Route path="/entrar" element={<Login />} />
        <Route path="*" element={<Navigate to="/entrar" replace state={{ de: local.pathname }} />} />
      </Routes>
    );
  }
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      {!largo && (
        <AppBar position="fixed" sx={{ borderBottom: 1, borderColor: "divider" }}>
          <Toolbar>
            <IconButton edge="start" onClick={() => setAberto(true)} aria-label="abrir menu"><MenuIcon /></IconButton>
            <Box sx={{ color: "primary.main", ml: 1, mr: 1.5, display: "flex" }}><Marca tamanho={28} /></Box>
            <Typography fontWeight={700}>FIEP</Typography>
          </Toolbar>
        </AppBar>
      )}
      <Drawer variant={largo ? "permanent" : "temporary"} open={largo || aberto} onClose={() => setAberto(false)}
              sx={{ width: LARGURA, flexShrink: 0, "& .MuiDrawer-paper": { width: LARGURA, boxSizing: "border-box" } }}>
        <Menu aoNavegar={() => setAberto(false)} />
      </Drawer>
      <Box component="main" sx={{ flex: 1, minWidth: 0, px: { xs: 2, sm: 3, lg: 4 }, pt: { xs: 10, md: 4 }, pb: 6, maxWidth: 1280 }}>
        <Routes>
          <Route path="/" element={<Painel />} />
          <Route path="/coletas" element={<Coletas />} />
          <Route path="/coletas/nova" element={pode("editar") ? <NovaColeta /> : <Navigate to="/coletas" />} />
          <Route path="/coletas/:id" element={<ColetaDetalhe />} />
          <Route path="/amostras" element={<Amostras />} />
          <Route path="/amostras/:id" element={<AmostraDetalhe />} />
          <Route path="/prever" element={<Prever />} />
          <Route path="/empresas" element={<Empresas />} />
          <Route path="/usuarios" element={pode("admin") ? <Usuarios /> : <Navigate to="/" />} />
          <Route path="/conta" element={<Conta />} />
          <Route path="/entrar" element={<Navigate to={(local.state as { de?: string })?.de || "/"} replace />} />
          <Route path="*" element={<Typography>Página não encontrada.</Typography>} />
        </Routes>
      </Box>
    </Box>
  );
}
