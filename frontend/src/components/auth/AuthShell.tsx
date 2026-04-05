import { Box, Container, Paper } from "@mui/material";
import { alpha } from "@mui/material/styles";

type AuthShellProps = {
    sideContent: React.ReactNode;
    children: React.ReactNode;
};

export function AuthShell({ sideContent, children }: AuthShellProps) {
    return (
        <Box
            sx={(theme) => ({
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                px: { xs: 2, md: 3 },
                py: { xs: 3, md: 4 },
                background: theme.palette.mode === "dark"
                    ? "linear-gradient(180deg, rgba(27, 27, 27, 0.98) 0%, rgba(18, 18, 18, 1) 100%)"
                    : "linear-gradient(180deg, rgba(246, 246, 246, 0.98) 0%, rgba(228, 228, 228, 1) 100%)",
            })}
        >
            <Container maxWidth="xl" sx={{ px: "0 !important" }}>
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.08fr) minmax(420px, 0.92fr)" },
                        gap: { xs: 2.5, lg: 3 },
                        alignItems: "stretch",
                    }}
                >
                    <Paper
                        sx={(theme) => ({
                            p: { xs: 3, md: 4.5 },
                            borderRadius: { xs: 4, md: 6 },
                            overflow: "hidden",
                            position: "relative",
                            color: "#F6F6F6",
                            background: "linear-gradient(145deg, #FE7023 0%, #D95B17 42%, #1B1B1B 100%)",
                            boxShadow:
                                theme.palette.mode === "dark"
                                    ? "0 24px 70px rgba(0, 0, 0, 0.48)"
                                    : "0 28px 70px rgba(254, 112, 35, 0.24)",
                            "&::before": {
                                content: '""',
                                position: "absolute",
                                inset: "auto auto -28% -14%",
                                width: 320,
                                height: 320,
                                borderRadius: "50%",
                                backgroundColor: alpha("#F6F6F6", 0.12),
                            },
                            "&::after": {
                                content: '""',
                                position: "absolute",
                                inset: "-20% -10% auto auto",
                                width: 280,
                                height: 280,
                                borderRadius: "50%",
                                backgroundColor: alpha("#F6F6F6", 0.1),
                            },
                        })}
                    >
                        <Box sx={{ position: "relative", zIndex: 1, height: "100%" }}>
                            {sideContent}
                        </Box>
                    </Paper>
                    <Paper
                        sx={{
                            p: { xs: 3, md: 4 },
                            borderRadius: { xs: 4, md: 6 },
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            minHeight: { lg: 720 },
                        }}
                    >
                        <Box sx={{ width: "100%", maxWidth: 440 }}>{children}</Box>
                    </Paper>
                </Box>
            </Container>
        </Box>
    );
}
