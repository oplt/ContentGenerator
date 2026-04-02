import { alpha, createTheme, type PaletteMode } from "@mui/material/styles";

function buildTheme(mode: PaletteMode) {
    const isDark = mode === "dark";
    const brandOrange = "#FE7023";
    const ink = "#1B1B1B";
    const mist = "#E4E4E4";
    const canvas = "#F6F6F6";

    const theme = createTheme({
        palette: {
            mode,
            primary: {
                main: brandOrange,
                light: "#FF935D",
                dark: "#D95B17",
                contrastText: ink,
            },
            secondary: {
                main: isDark ? mist : "#5D5D5D",
                light: isDark ? canvas : "#848484",
                dark: isDark ? "#CFCFCF" : ink,
            },
            success: {
                main: isDark ? "#6AC88E" : "#2F8F57",
            },
            warning: {
                main: isDark ? "#FFB37F" : "#D27A34",
            },
            error: {
                main: isDark ? "#F28A78" : "#C84A37",
            },
            background: {
                default: isDark ? ink : canvas,
                paper: isDark ? "#232323" : "#FBFBFB",
            },
            text: {
                primary: isDark ? canvas : ink,
                secondary: isDark ? "#C3C3C3" : "#5E5E5E",
            },
            divider: isDark ? alpha(mist, 0.14) : mist,
        },
        shape: {
            borderRadius: 2,
        },
        typography: {
            fontFamily: '"Manrope", "Segoe UI", sans-serif',
            h1: {
                fontSize: "clamp(2.6rem, 6vw, 4.6rem)",
                fontWeight: 800,
                letterSpacing: "-0.06em",
                lineHeight: 0.96,
            },
            h2: {
                fontSize: "clamp(2.2rem, 4vw, 3.4rem)",
                fontWeight: 800,
                letterSpacing: "-0.05em",
                lineHeight: 1,
            },
            h3: {
                fontSize: "clamp(1.85rem, 3vw, 2.6rem)",
                fontWeight: 800,
                letterSpacing: "-0.04em",
                lineHeight: 1.08,
            },
            h4: {
                fontSize: "clamp(1.55rem, 2vw, 2rem)",
                fontWeight: 780,
                letterSpacing: "-0.035em",
                lineHeight: 1.14,
            },
            h5: {
                fontSize: "1.25rem",
                fontWeight: 760,
                letterSpacing: "-0.03em",
                lineHeight: 1.2,
            },
            h6: {
                fontSize: "1.05rem",
                fontWeight: 760,
                letterSpacing: "-0.02em",
                lineHeight: 1.3,
            },
            subtitle1: {
                fontSize: "0.98rem",
                fontWeight: 700,
                letterSpacing: "-0.015em",
            },
            subtitle2: {
                fontSize: "0.87rem",
                fontWeight: 700,
                letterSpacing: "0.01em",
            },
            body1: {
                fontSize: "0.98rem",
                lineHeight: 1.6,
            },
            body2: {
                fontSize: "0.9rem",
                lineHeight: 1.6,
            },
            button: {
                fontSize: "0.95rem",
                fontWeight: 700,
                letterSpacing: "-0.01em",
                textTransform: "none",
            },
            overline: {
                fontSize: "0.72rem",
                fontWeight: 800,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
            },
            caption: {
                fontSize: "0.78rem",
                lineHeight: 1.45,
            },
        },
    });

    return createTheme(theme, {
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    ":root": {
                        colorScheme: mode,
                    },
                    "*, *::before, *::after": {
                        boxSizing: "border-box",
                    },
                    html: {
                        minHeight: "100%",
                        scrollBehavior: "smooth",
                    },
                    body: {
                        minHeight: "100vh",
                        margin: 0,
                        backgroundColor: theme.palette.background.default,
                        backgroundImage: isDark
                            ? `radial-gradient(circle at top left, ${alpha(brandOrange, 0.22)}, transparent 26%), radial-gradient(circle at 78% 2%, ${alpha(mist, 0.06)}, transparent 22%), linear-gradient(180deg, #1B1B1B 0%, #151515 100%)`
                            : `radial-gradient(circle at top left, ${alpha(brandOrange, 0.14)}, transparent 25%), radial-gradient(circle at 78% 2%, ${alpha(ink, 0.04)}, transparent 20%), linear-gradient(180deg, #F6F6F6 0%, #EEEEEE 100%)`,
                        color: theme.palette.text.primary,
                        textRendering: "optimizeLegibility",
                        WebkitFontSmoothing: "antialiased",
                        MozOsxFontSmoothing: "grayscale",
                    },
                    "#root": {
                        minHeight: "100vh",
                    },
                    "::selection": {
                        backgroundColor: alpha(theme.palette.primary.main, 0.22),
                    },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: {
                        backdropFilter: "blur(20px)",
                        backgroundImage: "none",
                    },
                },
            },
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
                    rounded: {
                        borderRadius: theme.shape.borderRadius,
                    },
                },
            },
            MuiCard: {
                defaultProps: {
                    elevation: 0,
                },
                styleOverrides: {
                    root: {
                        borderRadius: Number(theme.shape.borderRadius) + 1,
                        border: `1px solid ${theme.palette.divider}`,
                        backgroundColor: alpha(theme.palette.background.paper, isDark ? 0.8 : 0.92),
                        boxShadow: isDark
                            ? "0 18px 44px rgba(0, 0, 0, 0.38)"
                            : "0 18px 36px rgba(27, 27, 27, 0.08)",
                    },
                },
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        minHeight: 44,
                        paddingInline: 18,
                        borderRadius: 999,
                    },
                    contained: {
                        boxShadow: isDark
                            ? "0 16px 30px rgba(254, 112, 35, 0.24)"
                            : "0 14px 28px rgba(254, 112, 35, 0.22)",
                    },
                    outlined: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.16 : 0.12),
                        backgroundColor: alpha(theme.palette.background.paper, isDark ? 0.74 : 0.82),
                    },
                    text: {
                        color: theme.palette.text.primary,
                    },
                    sizeSmall: {
                        minHeight: 36,
                        paddingInline: 14,
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: 999,
                        fontWeight: 700,
                    },
                    outlined: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.12 : 0.1),
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        borderRadius: 3,
                        backgroundColor: isDark
                            ? alpha(canvas, 0.04)
                            : alpha("#FFFFFF", 0.9),
                        transition: theme.transitions.create(["border-color", "box-shadow", "background-color"]),
                        "&:hover .MuiOutlinedInput-notchedOutline": {
                            borderColor: alpha(theme.palette.primary.main, 0.34),
                        },
                        "&.Mui-focused": {
                            boxShadow: `0 0 0 4px ${alpha(theme.palette.primary.main, 0.14)}`,
                        },
                    },
                    notchedOutline: {
                        borderColor: alpha(theme.palette.text.primary, isDark ? 0.14 : 0.12),
                    },
                    input: {
                        paddingBlock: 14,
                    },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: {
                        fontWeight: 600,
                    },
                },
            },
            MuiAlert: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                    },
                    standardInfo: {
                        backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                    },
                },
            },
            MuiAvatar: {
                styleOverrides: {
                    root: {
                        fontWeight: 800,
                    },
                },
            },
            MuiDrawer: {
                styleOverrides: {
                    paper: {
                        borderRight: "none",
                        backgroundColor: alpha(theme.palette.background.paper, isDark ? 0.82 : 0.94),
                        backdropFilter: "blur(22px)",
                    },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        borderRadius: 16,
                        minHeight: 48,
                        "&.Mui-selected": {
                            backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.18 : 0.1),
                            color: theme.palette.primary.main,
                            "& .MuiListItemIcon-root": {
                                color: theme.palette.primary.main,
                            },
                        },
                        "&:hover": {
                            backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.12 : 0.06),
                        },
                    },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    head: {
                        fontWeight: 800,
                        color: theme.palette.text.secondary,
                        backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.1 : 0.04),
                    },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        borderRadius: 3,
                        backgroundColor: alpha(theme.palette.text.primary, 0.9),
                        color: theme.palette.background.paper,
                        fontSize: "0.78rem",
                    },
                },
            },
            MuiSkeleton: {
                defaultProps: {
                    animation: "wave",
                },
            },
        },
    });
}

export const lightTheme = buildTheme("light");
export const darkTheme = buildTheme("dark");

export type ColorMode = "light" | "dark" | "system";
