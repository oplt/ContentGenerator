import { useState } from "react";
import dayjs, { type Dayjs } from "dayjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    Drawer,
    MenuItem,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    AssignmentTurnedIn as TaskIcon,
    ChevronLeft as ChevronLeftIcon,
    ChevronRight as ChevronRightIcon,
    Event as EventIcon,
    Schedule as AppointmentIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { DateCalendar, PickersDay, type PickersDayProps } from "@mui/x-date-pickers";
import type {} from "@mui/x-date-pickers/AdapterDayjs";
import { createCalendarItem, listCalendarItems, type CalendarItem, type CalendarItemType } from "../../api/calendar";
import type { Project, ProjectTaskPriority } from "../../api/projects";
import { useSnackbar } from "../../app/snackbarContext";
import { formatDateOnly, humanizeKey } from "../../utils/formatters";
import { EmptyState } from "../ui/EmptyState";
import { SectionCard } from "../ui/SectionCard";

type CalendarViewMode = "day" | "week" | "month" | "twelve_month";

type DashboardCalendarProps = {
    projects: Project[];
    projectsLoading: boolean;
    onOpenProjects: () => void;
    allowedViews?: CalendarViewMode[];
    initialView?: CalendarViewMode;
};

type CalendarDraft = {
    type: CalendarItemType;
    title: string;
    description: string;
    start_time: string;
    end_time: string;
    project_id: string;
    priority: ProjectTaskPriority;
};

const VIEW_OPTIONS: Array<{ value: CalendarViewMode; label: string }> = [
    { value: "day", label: "Day" },
    { value: "week", label: "Week" },
    { value: "month", label: "Month" },
    { value: "twelve_month", label: "12M" },
];
const ITEM_TYPE_OPTIONS: Array<{ value: CalendarItemType; label: string }> = [
    { value: "event", label: "Event" },
    { value: "appointment", label: "Appointment" },
    { value: "task", label: "Task" },
];
const TASK_PRIORITY_OPTIONS: ProjectTaskPriority[] = ["low", "medium", "high", "urgent"];

function buildEmptyDraft(projects: Project[], type: CalendarItemType = "event"): CalendarDraft {
    return {
        type,
        title: "",
        description: "",
        start_time: "",
        end_time: "",
        project_id: projects[0]?.id ?? "",
        priority: "medium",
    };
}

function formatTimeValue(value: string) {
    return new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
    }).format(new Date(`1970-01-01T${value}`));
}

function formatItemTime(item: CalendarItem) {
    if (!item.start_time) {
        return item.type === "task" ? "Due anytime" : "All day";
    }
    if (!item.end_time) {
        return formatTimeValue(item.start_time);
    }
    return `${formatTimeValue(item.start_time)} to ${formatTimeValue(item.end_time)}`;
}

function getMinutesFromTimeString(value: string) {
    const [hours = "0", minutes = "0"] = value.split(":");
    return Number(hours) * 60 + Number(minutes);
}

function getWeekItemColor(item: CalendarItem) {
    if (item.type === "task") {
        return {
            bg: "#ecfdf3",
            border: "#a6f4c5",
            text: "#027a48",
        };
    }
    if (item.type === "appointment") {
        return {
            bg: "#f4f3ff",
            border: "#d9d6fe",
            text: "#7a22ff",
        };
    }
    return {
        bg: "#eef4ff",
        border: "#b2ddff",
        text: "#175cd3",
    };
}

function getItemIcon(type: CalendarItemType) {
    if (type === "task") {
        return <TaskIcon fontSize="small" />;
    }
    if (type === "appointment") {
        return <AppointmentIcon fontSize="small" />;
    }
    return <EventIcon fontSize="small" />;
}

function getDateCalendarSx(daySize: number) {
    return {
        width: "100%",
        maxWidth: "none",
        m: 0,
        "& .MuiPickersCalendarHeader-root": {
            px: 1,
            mb: 0.5,
        },
        "& .MuiPickersCalendarHeader-switchViewButton": {
            display: "none",
        },
        "& .MuiPickersCalendarHeader-label": {
            fontSize: "1rem",
            fontWeight: 700,
        },
        "& .MuiDayCalendar-header": {
            justifyContent: "space-between",
            px: 0.75,
        },
        "& .MuiDayCalendar-weekDayLabel": {
            width: daySize,
            color: "text.secondary",
            fontWeight: 700,
        },
        "& .MuiDayCalendar-weekContainer": {
            justifyContent: "space-between",
            mt: 0.5,
        },
    } as const;
}

function getMonthGridColumns(viewMode: CalendarViewMode) {
    if (viewMode === "twelve_month") {
        return {
            xs: "1fr",
            md: "repeat(2, minmax(0, 1fr))",
            xl: "repeat(4, minmax(0, 1fr))",
        } as const;
    }

    return { xs: "1fr" } as const;
}

function getQueryRange(viewMode: CalendarViewMode, anchorDate: Dayjs) {
    if (viewMode === "day") {
        const dateKey = anchorDate.startOf("day").format("YYYY-MM-DD");
        return { start: dateKey, end: dateKey };
    }

    if (viewMode === "week") {
        return {
            start: anchorDate.startOf("week").format("YYYY-MM-DD"),
            end: anchorDate.endOf("week").format("YYYY-MM-DD"),
        };
    }

    if (viewMode === "twelve_month") {
        const startMonth = anchorDate.startOf("month");
        const endMonth = startMonth.add(11, "month");
        return {
            start: startMonth.startOf("month").startOf("week").format("YYYY-MM-DD"),
            end: endMonth.endOf("month").endOf("week").format("YYYY-MM-DD"),
        };
    }

    return {
        start: anchorDate.startOf("month").startOf("week").format("YYYY-MM-DD"),
        end: anchorDate.endOf("month").endOf("week").format("YYYY-MM-DD"),
    };
}

function shiftAnchorDate(current: Dayjs, viewMode: CalendarViewMode, direction: 1 | -1) {
    if (viewMode === "day") {
        return current.add(direction, "day");
    }
    if (viewMode === "week") {
        return current.add(direction, "week");
    }
    if (viewMode === "twelve_month") {
        return current.add(direction * 12, "month");
    }
    return current.add(direction, "month");
}

function DayItems({
    items,
    emptyTitle,
    emptyDescription,
}: {
    items: CalendarItem[];
    emptyTitle: string;
    emptyDescription: string;
}) {
    if (items.length === 0) {
        return (
            <EmptyState
                icon={<EventIcon />}
                title={emptyTitle}
                description={emptyDescription}
            />
        );
    }

    return (
        <Stack spacing={1}>
            {items.map((item) => (
                <Box
                    key={item.id}
                    sx={(theme) => ({
                        borderRadius: 3,
                        border: `1px solid ${theme.palette.divider}`,
                        p: 1.5,
                        backgroundColor:
                            item.type === "task"
                                ? alpha(theme.palette.success.main, theme.palette.mode === "dark" ? 0.16 : 0.08)
                                : theme.palette.background.paper,
                    })}
                >
                    <Stack spacing={0.75}>
                        <Stack direction="row" spacing={1} alignItems="center">
                            {getItemIcon(item.type)}
                            <Typography variant="subtitle2">{item.title}</Typography>
                        </Stack>
                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                            <Chip label={humanizeKey(item.type)} size="small" variant="outlined" />
                            <Chip label={formatItemTime(item)} size="small" variant="outlined" />
                            {item.project_name && (
                                <Chip label={item.project_name} size="small" variant="outlined" />
                            )}
                            {item.status && (
                                <Chip label={humanizeKey(item.status)} size="small" variant="outlined" />
                            )}
                            {item.priority && (
                                <Chip
                                    label={`${humanizeKey(item.priority)} priority`}
                                    size="small"
                                    variant="outlined"
                                />
                            )}
                        </Stack>
                        {item.description && (
                            <Typography variant="body2" color="text.secondary">
                                {item.description}
                            </Typography>
                        )}
                    </Stack>
                </Box>
            ))}
        </Stack>
    );
}

export function DashboardCalendar({
    projects,
    projectsLoading,
    onOpenProjects,
    allowedViews = ["month"],
    initialView = "month",
}: DashboardCalendarProps) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [viewMode, setViewMode] = useState<CalendarViewMode>(initialView);
    const [anchorDate, setAnchorDate] = useState(dayjs().startOf("day"));
    const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [draft, setDraft] = useState<CalendarDraft>(buildEmptyDraft(projects));
    const [formError, setFormError] = useState("");

    const { start, end } = getQueryRange(viewMode, anchorDate);
    const selectedDate = selectedDateKey ? dayjs(selectedDateKey) : anchorDate;
    const visibleMonths =
        viewMode === "twelve_month"
            ? Array.from({ length: 12 }, (_, index) => anchorDate.startOf("month").add(index, "month"))
            : [anchorDate.startOf("month")];
    const daySize = viewMode === "twelve_month" ? 34 : 40;

    const { data: calendarItems, isLoading, error } = useQuery({
        queryKey: ["calendar", "items", start, end],
        queryFn: () => listCalendarItems(start, end),
    });

    const itemsByDate = (calendarItems ?? []).reduce<Record<string, CalendarItem[]>>((accumulator, item) => {
        accumulator[item.date] = [...(accumulator[item.date] ?? []), item];
        return accumulator;
    }, {});

    const createItemMutation = useMutation({
        mutationFn: () =>
            createCalendarItem({
                type: draft.type,
                title: draft.title.trim(),
                description: draft.description.trim() || null,
                date: selectedDateKey ?? anchorDate.format("YYYY-MM-DD"),
                start_time: draft.type === "task" ? null : draft.start_time || null,
                end_time: draft.type === "task" ? null : draft.end_time || null,
                project_id: draft.type === "task" ? draft.project_id || null : null,
                priority: draft.type === "task" ? draft.priority : null,
            }),
        onSuccess: async (item) => {
            await queryClient.invalidateQueries({ queryKey: ["calendar", "items"] });
            if (item.type === "task") {
                await queryClient.invalidateQueries({ queryKey: ["projects"] });
            }
            setDraft(buildEmptyDraft(projects, draft.type));
            setFormError("");
            showToast({
                message:
                    item.type === "task"
                        ? "Task scheduled on the calendar."
                        : `${humanizeKey(item.type)} saved.`,
                severity: "success",
            });
        },
        onError: (mutationError) => {
            setFormError(
                mutationError instanceof Error ? mutationError.message : "Failed to save calendar item."
            );
        },
    });

    function openDay(value: Dayjs | string) {
        const nextDate = typeof value === "string" ? dayjs(value) : value.startOf("day");
        setSelectedDateKey(nextDate.format("YYYY-MM-DD"));
        setAnchorDate(nextDate);
        setDrawerOpen(true);
        setFormError("");
        setDraft((current) => ({
            ...current,
            project_id: current.project_id || projects[0]?.id || "",
        }));
    }

    function submitDraft() {
        if (!selectedDateKey) {
            setFormError("Choose a day before adding a calendar item.");
            return;
        }
        if (draft.title.trim().length < 2) {
            setFormError("Title must be at least 2 characters.");
            return;
        }
        if (draft.type === "task" && !draft.project_id) {
            setFormError("Select a project for this task.");
            return;
        }
        if (draft.type !== "task" && draft.end_time && !draft.start_time) {
            setFormError("Start time is required when end time is set.");
            return;
        }
        if (
            draft.type !== "task" &&
            draft.start_time &&
            draft.end_time &&
            draft.end_time <= draft.start_time
        ) {
            setFormError("End time must be after start time.");
            return;
        }
        createItemMutation.mutate();
    }

    function CalendarDay(props: PickersDayProps) {
        const { day, outsideCurrentMonth, ...other } = props;
        const dateKey = day.format("YYYY-MM-DD");
        const dayItems = itemsByDate[dateKey] ?? [];

        return (
            <Box sx={{ position: "relative" }}>
                <PickersDay
                    {...other}
                    day={day}
                    outsideCurrentMonth={outsideCurrentMonth}
                    disableMargin
                    onClick={(event) => {
                        other.onClick?.(event);
                        openDay(day);
                    }}
                    sx={(theme) => ({
                        width: daySize,
                        height: daySize,
                        fontWeight: 700,
                        borderRadius: "999px",
                        color: outsideCurrentMonth
                            ? theme.palette.text.disabled
                            : theme.palette.text.primary,
                        backgroundColor: "transparent",
                        border: 0,
                        "&.Mui-selected": {
                            backgroundColor: theme.palette.primary.main,
                            color: theme.palette.primary.contrastText,
                        },
                        "&.Mui-selected:hover": {
                            backgroundColor: theme.palette.primary.dark,
                        },
                        "&.MuiPickersDay-today": {
                            border: 0,
                            backgroundColor: alpha(
                                theme.palette.secondary.main,
                                theme.palette.mode === "dark" ? 0.2 : 0.1
                            ),
                        },
                        "&:hover": {
                            backgroundColor: alpha(
                                theme.palette.primary.main,
                                theme.palette.mode === "dark" ? 0.14 : 0.08
                            ),
                        },
                    })}
                />
                {dayItems.length > 0 && (
                    <Stack
                        direction="row"
                        spacing={0.35}
                        justifyContent="center"
                        alignItems="center"
                        sx={{
                            position: "absolute",
                            left: "50%",
                            bottom: -2,
                            transform: "translateX(-50%)",
                            pointerEvents: "none",
                        }}
                    >
                        {dayItems.slice(0, 3).map((item) => (
                            <Box
                                key={item.id}
                                sx={(theme) => ({
                                    width: 5,
                                    height: 5,
                                    borderRadius: "999px",
                                    backgroundColor:
                                        item.type === "task"
                                            ? theme.palette.success.main
                                            : item.type === "appointment"
                                                ? theme.palette.secondary.main
                                                : theme.palette.primary.main,
                                })}
                            />
                        ))}
                    </Stack>
                )}
            </Box>
        );
    }

    function renderDateCalendar(date: Dayjs) {
        return (
            <DateCalendar
                value={selectedDate.isSame(date, "month") ? selectedDate : null}
                onChange={(newValue) => {
                    if (newValue) {
                        setAnchorDate(newValue.startOf("day"));
                    }
                }}
                referenceDate={date}
                views={["day"]}
                showDaysOutsideCurrentMonth
                fixedWeekNumber={6}
                reduceAnimations
                slots={{ day: CalendarDay }}
                sx={getDateCalendarSx(daySize)}
            />
        );
    }

    function renderDayView() {
        const dayKey = anchorDate.format("YYYY-MM-DD");
        const dayItems = itemsByDate[dayKey] ?? [];
        const timedItems = dayItems
            .filter((item) => item.start_time)
            .map((item) => {
                const startMinutes = getMinutesFromTimeString(item.start_time ?? "09:00");
                const endMinutes = item.end_time
                    ? getMinutesFromTimeString(item.end_time)
                    : startMinutes + 60;
                const clampedEnd = Math.max(endMinutes, startMinutes + 30);

                return {
                    ...item,
                    startMinutes,
                    endMinutes: clampedEnd,
                };
            });
        const allDayItems = dayItems.filter((item) => !item.start_time);
        const hourSlots = Array.from({ length: 24 }, (_, index) => index);
        const rowHeight = 56;
        const gridStartMinutes = 0;
        const now = dayjs();
        const isToday = anchorDate.isSame(now, "day");
        const nowMinutes = now.hour() * 60 + now.minute();
        const nowTop = (nowMinutes / 60) * rowHeight;
        const selectedDetailItem = timedItems[0] ?? allDayItems[0] ?? dayItems[0] ?? null;

        return (
            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.5fr) 360px" },
                }}
            >
                <Box
                    sx={(theme) => ({
                        borderRadius: 4,
                        border: `1px solid ${theme.palette.divider}`,
                        overflow: "hidden",
                        backgroundColor: theme.palette.background.paper,
                    })}
                >
                    <Stack
                        direction={{ xs: "column", sm: "row" }}
                        justifyContent="space-between"
                        spacing={1.5}
                        sx={(theme) => ({
                            px: 2,
                            py: 1.5,
                            borderBottom: `1px solid ${theme.palette.divider}`,
                            backgroundColor: theme.palette.background.default,
                        })}
                    >
                        <Box>
                            <Typography variant="h6">{formatDateOnly(dayKey)}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Focused view for one day of scheduled work.
                            </Typography>
                        </Box>
                        <Button variant="contained" onClick={() => openDay(anchorDate)}>
                            Add item
                        </Button>
                    </Stack>

                    {allDayItems.length > 0 && (
                        <Box
                            sx={(theme) => ({
                                px: 2,
                                py: 1.25,
                                borderBottom: `1px solid ${theme.palette.divider}`,
                                backgroundColor: theme.palette.background.paper,
                            })}
                        >
                            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                                All day
                            </Typography>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                {allDayItems.map((item) => {
                                    const colors = getWeekItemColor(item);
                                    return (
                                        <Box
                                            key={item.id}
                                            onClick={() => openDay(anchorDate)}
                                            sx={{
                                                px: 1.25,
                                                py: 0.8,
                                                borderRadius: 2,
                                                border: `1px solid ${colors.border}`,
                                                backgroundColor: colors.bg,
                                                color: colors.text,
                                                cursor: "pointer",
                                            }}
                                        >
                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                {item.title}
                                            </Typography>
                                        </Box>
                                    );
                                })}
                            </Stack>
                        </Box>
                    )}

                    <Box
                        sx={{
                            display: "grid",
                            gridTemplateColumns: "88px minmax(0, 1fr)",
                            minHeight: rowHeight * hourSlots.length,
                            maxHeight: 760,
                            overflow: "auto",
                        }}
                    >
                        <Box
                            sx={(theme) => ({
                                borderRight: `1px solid ${theme.palette.divider}`,
                                backgroundColor: theme.palette.background.default,
                            })}
                        >
                            {hourSlots.map((hour) => (
                                <Box
                                    key={hour}
                                    sx={(theme) => ({
                                        height: rowHeight,
                                        px: 1.25,
                                        pt: 0.55,
                                        borderBottom: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
                                        {dayjs().hour(hour).minute(0).format("h A")}
                                    </Typography>
                                </Box>
                            ))}
                        </Box>
                        <Box
                            sx={(theme) => ({
                                position: "relative",
                                backgroundColor: theme.palette.background.paper,
                            })}
                        >
                            {hourSlots.map((hour) => (
                                <Box
                                    key={hour}
                                    sx={(theme) => ({
                                        height: rowHeight,
                                        borderBottom: `1px solid ${theme.palette.divider}`,
                                    })}
                                />
                            ))}

                            {isToday && (
                                <Box
                                    sx={{
                                        position: "absolute",
                                        left: 0,
                                        right: 0,
                                        top: nowTop,
                                        height: 2,
                                        backgroundColor: "primary.main",
                                        zIndex: 2,
                                        "&::before": {
                                            content: '""',
                                            position: "absolute",
                                            left: -6,
                                            top: "50%",
                                            width: 10,
                                            height: 10,
                                            borderRadius: "999px",
                                            backgroundColor: "primary.main",
                                            transform: "translateY(-50%)",
                                        },
                                    }}
                                />
                            )}

                            {timedItems.map((item) => {
                                const colors = getWeekItemColor(item);
                                const top = ((item.startMinutes - gridStartMinutes) / 60) * rowHeight;
                                const height = Math.max(
                                    ((item.endMinutes - item.startMinutes) / 60) * rowHeight,
                                    44
                                );

                                return (
                                    <Box
                                        key={item.id}
                                        onClick={() => openDay(anchorDate)}
                                        sx={{
                                            position: "absolute",
                                            top,
                                            left: 12,
                                            right: 12,
                                            height,
                                            px: 1.25,
                                            py: 1,
                                            borderRadius: 2,
                                            border: `1px solid ${colors.border}`,
                                            backgroundColor: colors.bg,
                                            color: colors.text,
                                            cursor: "pointer",
                                            overflow: "hidden",
                                            zIndex: 1,
                                        }}
                                    >
                                        <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                                            {item.title}
                                        </Typography>
                                        <Typography variant="body2" sx={{ mt: 0.4 }}>
                                            {formatItemTime(item)}
                                        </Typography>
                                    </Box>
                                );
                            })}
                        </Box>
                    </Box>
                </Box>

                <Box
                    sx={(theme) => ({
                        borderRadius: 4,
                        border: `1px solid ${theme.palette.divider}`,
                        overflow: "hidden",
                        backgroundColor: theme.palette.background.paper,
                    })}
                >
                    <Box
                        sx={(theme) => ({
                            p: 1.25,
                            borderBottom: `1px solid ${theme.palette.divider}`,
                            backgroundColor: alpha(
                                theme.palette.background.paper,
                                theme.palette.mode === "dark" ? 0.9 : 0.78
                            ),
                        })}
                    >
                        {renderDateCalendar(anchorDate)}
                    </Box>
                    <Box sx={{ p: 2 }}>
                        {selectedDetailItem ? (
                            <Stack spacing={2}>
                                <Box>
                                    <Typography variant="h6">{selectedDetailItem.title}</Typography>
                                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                        {selectedDetailItem.description || "No extra notes for this item."}
                                    </Typography>
                                </Box>
                                <Stack spacing={1}>
                                    <Typography variant="body2" color="text.secondary">
                                        {formatDateOnly(dayKey)}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        {formatItemTime(selectedDetailItem)}
                                    </Typography>
                                    {selectedDetailItem.project_name && (
                                        <Typography variant="body2" color="text.secondary">
                                            Project: {selectedDetailItem.project_name}
                                        </Typography>
                                    )}
                                    {selectedDetailItem.priority && (
                                        <Typography variant="body2" color="text.secondary">
                                            Priority: {humanizeKey(selectedDetailItem.priority)}
                                        </Typography>
                                    )}
                                </Stack>
                                <Button variant="outlined" onClick={() => openDay(anchorDate)}>
                                    Edit or add item
                                </Button>
                            </Stack>
                        ) : (
                            <DayItems
                                items={dayItems}
                                emptyTitle="Nothing scheduled for this day"
                                emptyDescription="Use Add item to create an event, appointment, or task."
                            />
                        )}
                    </Box>
                </Box>
            </Box>
        );
    }

    function renderWeekView() {
        const weekDays = Array.from({ length: 7 }, (_, index) =>
            anchorDate.startOf("week").add(index, "day")
        );
        const hourSlots = Array.from({ length: 10 }, (_, index) => 9 + index);
        const rowHeight = 88;
        const dayColumnWidth = 194;

        const timedWeekItems = weekDays.map((day) => {
            const dateKey = day.format("YYYY-MM-DD");
            return (itemsByDate[dateKey] ?? [])
                .filter((item) => item.start_time)
                .map((item) => {
                    const startMinutes = getMinutesFromTimeString(item.start_time ?? "09:00");
                    const endMinutes = item.end_time
                        ? getMinutesFromTimeString(item.end_time)
                        : startMinutes + 60;
                    const clampedStart = Math.max(9 * 60, startMinutes);
                    const clampedEnd = Math.max(clampedStart + 30, endMinutes);

                    return {
                        ...item,
                        top: ((clampedStart - 9 * 60) / 60) * rowHeight,
                        height: Math.max(((clampedEnd - clampedStart) / 60) * rowHeight, 44),
                    };
                });
        });

        const allDayWeekItems = weekDays.map((day) => {
            const dateKey = day.format("YYYY-MM-DD");
            return (itemsByDate[dateKey] ?? []).filter((item) => !item.start_time);
        });

        return (
            <Box
                sx={(theme) => ({
                    borderRadius: 4,
                    border: `1px solid ${theme.palette.divider}`,
                    overflow: "hidden",
                    backgroundColor: theme.palette.background.paper,
                })}
            >
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: `88px repeat(7, minmax(${dayColumnWidth}px, 1fr))`,
                        minWidth: 980,
                    }}
                >
                    <Box
                        sx={(theme) => ({
                            borderRight: `1px solid ${theme.palette.divider}`,
                            borderBottom: `1px solid ${theme.palette.divider}`,
                            backgroundColor: theme.palette.background.default,
                        })}
                    />
                    {weekDays.map((day) => {
                        const isToday = day.isSame(dayjs(), "day");
                        return (
                            <Box
                                key={day.format("YYYY-MM-DD")}
                                sx={(theme) => ({
                                    minHeight: 88,
                                    px: 2,
                                    py: 1.5,
                                    borderRight: `1px solid ${theme.palette.divider}`,
                                    borderBottom: `1px solid ${theme.palette.divider}`,
                                    backgroundColor: theme.palette.background.default,
                                    display: "flex",
                                    alignItems: "flex-start",
                                    justifyContent: "center",
                                })}
                            >
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                        {day.format("ddd D")}
                                    </Typography>
                                    {isToday && (
                                        <Box
                                            sx={(theme) => ({
                                                width: 32,
                                                height: 32,
                                                borderRadius: "999px",
                                                display: "grid",
                                                placeItems: "center",
                                                backgroundColor: theme.palette.primary.main,
                                                color: theme.palette.primary.contrastText,
                                                fontSize: 14,
                                                fontWeight: 700,
                                            })}
                                        >
                                            {day.format("D")}
                                        </Box>
                                    )}
                                </Stack>
                            </Box>
                        );
                    })}

                    <Box
                        sx={(theme) => ({
                            minHeight: 64,
                            px: 1.5,
                            py: 1,
                            borderRight: `1px solid ${theme.palette.divider}`,
                            borderBottom: `1px solid ${theme.palette.divider}`,
                            backgroundColor: theme.palette.background.default,
                        })}
                    >
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                            All day
                        </Typography>
                    </Box>
                    {weekDays.map((day, dayIndex) => {
                        const allDayItems = allDayWeekItems[dayIndex];
                        return (
                            <Box
                                key={`${day.format("YYYY-MM-DD")}-all-day`}
                                sx={(theme) => ({
                                    minHeight: 64,
                                    p: 1,
                                    borderRight: `1px solid ${theme.palette.divider}`,
                                    borderBottom: `1px solid ${theme.palette.divider}`,
                                    backgroundColor: theme.palette.background.paper,
                                })}
                            >
                                <Stack spacing={0.75}>
                                    {allDayItems.slice(0, 2).map((item) => {
                                        const colors = getWeekItemColor(item);
                                        return (
                                            <Box
                                                key={item.id}
                                                onClick={() => openDay(day)}
                                                sx={{
                                                    px: 1.25,
                                                    py: 0.75,
                                                    borderRadius: 2,
                                                    border: `1px solid ${colors.border}`,
                                                    backgroundColor: colors.bg,
                                                    color: colors.text,
                                                    cursor: "pointer",
                                                }}
                                            >
                                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                    {item.title}
                                                </Typography>
                                            </Box>
                                        );
                                    })}
                                    {allDayItems.length > 2 && (
                                        <Typography variant="caption" color="text.secondary">
                                            +{allDayItems.length - 2} more
                                        </Typography>
                                    )}
                                </Stack>
                            </Box>
                        );
                    })}

                    <Box
                        sx={(theme) => ({
                            position: "relative",
                            borderRight: `1px solid ${theme.palette.divider}`,
                            backgroundColor: theme.palette.background.default,
                        })}
                    >
                        {hourSlots.map((hour) => (
                            <Box
                                key={hour}
                                sx={(theme) => ({
                                    height: rowHeight,
                                    px: 1.25,
                                    pt: 0.8,
                                    borderBottom: `1px solid ${theme.palette.divider}`,
                                })}
                            >
                                <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
                                    {dayjs().hour(hour).minute(0).format("h A")}
                                </Typography>
                            </Box>
                        ))}
                    </Box>
                    {weekDays.map((day, dayIndex) => (
                        <Box
                            key={`${day.format("YYYY-MM-DD")}-grid`}
                            sx={(theme) => ({
                                position: "relative",
                                height: rowHeight * hourSlots.length,
                                borderRight: `1px solid ${theme.palette.divider}`,
                                backgroundColor: theme.palette.background.paper,
                            })}
                        >
                            {hourSlots.map((hour) => (
                                <Box
                                    key={hour}
                                    sx={(theme) => ({
                                        height: rowHeight,
                                        borderBottom: `1px solid ${theme.palette.divider}`,
                                    })}
                                />
                            ))}
                            {timedWeekItems[dayIndex].map((item) => {
                                const colors = getWeekItemColor(item);
                                return (
                                    <Box
                                        key={item.id}
                                        onClick={() => openDay(day)}
                                        sx={{
                                            position: "absolute",
                                            top: item.top,
                                            left: 8,
                                            right: 8,
                                            height: item.height,
                                            px: 1.25,
                                            py: 1,
                                            borderRadius: 2,
                                            border: `1px solid ${colors.border}`,
                                            backgroundColor: colors.bg,
                                            color: colors.text,
                                            cursor: "pointer",
                                            overflow: "hidden",
                                        }}
                                    >
                                        <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                                            {item.title}
                                        </Typography>
                                        <Typography variant="body2" sx={{ mt: 0.4 }}>
                                            {formatTimeValue(item.start_time ?? "09:00")}
                                        </Typography>
                                    </Box>
                                );
                            })}
                        </Box>
                    ))}
                </Box>
            </Box>
        );
    }

    function renderMonthViews() {
        return (
            <Box
                sx={{
                    display: "grid",
                    gap: 1.5,
                    gridTemplateColumns: getMonthGridColumns(viewMode),
                }}
            >
                {visibleMonths.map((month) => (
                    <Box
                        key={month.format("YYYY-MM")}
                        sx={(theme) => ({
                            borderRadius: 4,
                            border: `1px solid ${theme.palette.divider}`,
                            p: 1.25,
                            backgroundColor: alpha(
                                theme.palette.background.paper,
                                theme.palette.mode === "dark" ? 0.9 : 0.78
                            ),
                        })}
                    >
                        {renderDateCalendar(month)}
                    </Box>
                ))}
            </Box>
        );
    }

    return (
        <>
            <SectionCard
                title="Workspace calendar"
                description="Switch between focused day planning, weekly scheduling, monthly scanning, and a 12-month horizon."
                action={
                    <Stack spacing={1} alignItems={{ xs: "stretch", sm: "flex-end" }}>
                        {allowedViews.length > 1 && (
                            <Stack
                                direction="row"
                                spacing={0.75}
                                flexWrap="wrap"
                                useFlexGap
                                justifyContent="flex-end"
                            >
                                {VIEW_OPTIONS.filter((option) => allowedViews.includes(option.value)).map((option) => (
                                    <Button
                                        key={option.value}
                                        size="small"
                                        variant={viewMode === option.value ? "contained" : "outlined"}
                                        onClick={() => setViewMode(option.value)}
                                    >
                                        {option.label}
                                    </Button>
                                ))}
                            </Stack>
                        )}
                        <Stack direction="row" spacing={0.75} justifyContent="flex-end">
                            <Button
                                size="small"
                                variant="text"
                                startIcon={<ChevronLeftIcon />}
                                onClick={() =>
                                    setAnchorDate((current) => shiftAnchorDate(current, viewMode, -1))
                                }
                            >
                                Back
                            </Button>
                            <Button
                                size="small"
                                variant="text"
                                endIcon={<ChevronRightIcon />}
                                onClick={() =>
                                    setAnchorDate((current) => shiftAnchorDate(current, viewMode, 1))
                                }
                            >
                                Forward
                            </Button>
                        </Stack>
                    </Stack>
                }
            >
                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error instanceof Error ? error.message : "Failed to load calendar items."}
                    </Alert>
                )}

                {isLoading ? (
                    viewMode === "day" || viewMode === "week" ? (
                        <Stack spacing={2}>
                            <Skeleton variant="rounded" height={340} sx={{ borderRadius: 4 }} />
                            <Skeleton variant="rounded" height={220} sx={{ borderRadius: 4 }} />
                        </Stack>
                    ) : (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: getMonthGridColumns(viewMode),
                            }}
                        >
                            {visibleMonths.map((month) => (
                                <Skeleton
                                    key={month.format("YYYY-MM")}
                                    variant="rounded"
                                    height={viewMode === "twelve_month" ? 360 : 420}
                                    sx={{ borderRadius: 4 }}
                                />
                            ))}
                        </Box>
                    )
                ) : viewMode === "day" ? (
                    renderDayView()
                ) : viewMode === "week" ? (
                    renderWeekView()
                ) : (
                    renderMonthViews()
                )}
            </SectionCard>

            <Drawer
                anchor="right"
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{
                    sx: {
                        width: { xs: "100%", sm: 420 },
                        p: 2.5,
                    },
                }}
            >
                <Stack spacing={2}>
                    <Box>
                        <Typography variant="h5" sx={{ mb: 0.5 }}>
                            {selectedDateKey ? formatDateOnly(selectedDateKey) : "Select a day"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Add an event, appointment, or a real task due on this day.
                        </Typography>
                    </Box>

                    <Divider />

                    <Box>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                            Day agenda
                        </Typography>
                        <DayItems
                            items={selectedDateKey ? itemsByDate[selectedDateKey] ?? [] : []}
                            emptyTitle="Nothing scheduled yet"
                            emptyDescription="Pick a type below and add the first calendar item for this day."
                        />
                    </Box>

                    <Divider />

                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Add new item</Typography>
                        <TextField
                            label="Type"
                            select
                            value={draft.type}
                            onChange={(event) => {
                                const nextType = event.target.value as CalendarItemType;
                                setDraft((current) => ({
                                    ...current,
                                    type: nextType,
                                    start_time: nextType === "task" ? "" : current.start_time,
                                    end_time: nextType === "task" ? "" : current.end_time,
                                    project_id: current.project_id || projects[0]?.id || "",
                                }));
                                setFormError("");
                            }}
                            fullWidth
                        >
                            {ITEM_TYPE_OPTIONS.map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Title"
                            value={draft.title}
                            onChange={(event) => {
                                setDraft((current) => ({ ...current, title: event.target.value }));
                                setFormError("");
                            }}
                            fullWidth
                        />
                        <TextField
                            label="Description"
                            value={draft.description}
                            onChange={(event) =>
                                setDraft((current) => ({ ...current, description: event.target.value }))
                            }
                            fullWidth
                            multiline
                            minRows={3}
                        />

                        {draft.type === "task" ? (
                            <>
                                <TextField
                                    label="Project"
                                    select
                                    value={draft.project_id}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, project_id: event.target.value }))
                                    }
                                    fullWidth
                                    disabled={projectsLoading}
                                    helperText={
                                        projects.length > 0
                                            ? "Task will be created in Todo with this date as its due date."
                                            : "Create a project first before scheduling tasks from the calendar."
                                    }
                                >
                                    {projects.map((project) => (
                                        <MenuItem key={project.id} value={project.id}>
                                            {project.name}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    label="Priority"
                                    select
                                    value={draft.priority}
                                    onChange={(event) =>
                                        setDraft((current) => ({
                                            ...current,
                                            priority: event.target.value as ProjectTaskPriority,
                                        }))
                                    }
                                    fullWidth
                                >
                                    {TASK_PRIORITY_OPTIONS.map((priority) => (
                                        <MenuItem key={priority} value={priority}>
                                            {humanizeKey(priority)}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                {projects.length === 0 && (
                                    <Button variant="outlined" onClick={onOpenProjects}>
                                        Create a project
                                    </Button>
                                )}
                            </>
                        ) : (
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25}>
                                <TextField
                                    label="Start time"
                                    type="time"
                                    value={draft.start_time}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, start_time: event.target.value }))
                                    }
                                    fullWidth
                                    InputLabelProps={{ shrink: true }}
                                />
                                <TextField
                                    label="End time"
                                    type="time"
                                    value={draft.end_time}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, end_time: event.target.value }))
                                    }
                                    fullWidth
                                    InputLabelProps={{ shrink: true }}
                                />
                            </Stack>
                        )}

                        {formError && <Alert severity="error">{formError}</Alert>}

                        <Stack direction="row" spacing={1}>
                            <Button variant="outlined" onClick={() => setDrawerOpen(false)} fullWidth>
                                Close
                            </Button>
                            <Button
                                variant="contained"
                                onClick={submitDraft}
                                disabled={
                                    createItemMutation.isPending ||
                                    (draft.type === "task" && projects.length === 0)
                                }
                                fullWidth
                            >
                                {createItemMutation.isPending ? "Saving..." : "Save"}
                            </Button>
                        </Stack>
                    </Stack>
                </Stack>
            </Drawer>
        </>
    );
}
