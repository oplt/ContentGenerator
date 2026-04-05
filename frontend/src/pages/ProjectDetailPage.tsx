import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    MenuItem,
    Paper,
    Skeleton,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    ArrowBack as ArrowBackIcon,
    AssignmentTurnedIn as DoneIcon,
    CalendarMonth as CalendarIcon,
    DeleteOutline as DeleteIcon,
    DragIndicator as DragIndicatorIcon,
    PlaylistAddCheck as TaskIcon,
    ViewKanban as BoardIcon,
    ViewList as ListIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate, useParams } from "react-router-dom";
import {
    createProjectTask,
    deleteProjectTask,
    getProject,
    listProjectTasks,
    reorderProjectTasks,
    type ProjectTask,
    type ProjectTaskPriority,
    type ProjectTaskStatus,
    updateProjectTask,
} from "../api/projects";
import { listUserDirectory } from "../api/users";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { formatDate, formatDateOnly, formatDateTime, humanizeKey } from "../utils/formatters";

type TaskDraft = {
    title: string;
    description: string;
    status: ProjectTaskStatus;
    priority: ProjectTaskPriority;
    due_date: string;
    assignee_id: string;
};

type TaskView = "board" | "list";

const EMPTY_TASK_DRAFT: TaskDraft = {
    title: "",
    description: "",
    status: "backlog",
    priority: "medium",
    due_date: "",
    assignee_id: "",
};

const TASK_STATUS_OPTIONS: Array<{ value: ProjectTaskStatus; label: string }> = [
    { value: "backlog", label: "Backlog" },
    { value: "todo", label: "Todo" },
    { value: "in_progress", label: "In progress" },
    { value: "review", label: "Review" },
    { value: "done", label: "Done" },
];

const TASK_PRIORITY_OPTIONS: Array<{ value: ProjectTaskPriority; label: string }> = [
    { value: "low", label: "Low" },
    { value: "medium", label: "Medium" },
    { value: "high", label: "High" },
    { value: "urgent", label: "Urgent" },
];

function sortTasks(tasks: ProjectTask[]) {
    const statusOrder: Record<ProjectTaskStatus, number> = {
        backlog: 0,
        todo: 1,
        in_progress: 2,
        review: 3,
        done: 4,
    };
    return [...tasks].sort(
        (left, right) =>
            statusOrder[left.status] - statusOrder[right.status] ||
            left.position - right.position ||
            left.created_at.localeCompare(right.created_at)
    );
}

function taskToDraft(task: ProjectTask): TaskDraft {
    return {
        title: task.title,
        description: task.description ?? "",
        status: task.status,
        priority: task.priority,
        due_date: task.due_date ?? "",
        assignee_id: task.assignee?.id ?? "",
    };
}

function TaskMetaChips({ task }: { task: ProjectTask }) {
    return (
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <Chip label={humanizeKey(task.status)} size="small" variant="outlined" />
            <Chip label={humanizeKey(task.priority)} size="small" variant="outlined" />
            {task.assignee && (
                <Chip
                    label={task.assignee.full_name || task.assignee.email}
                    size="small"
                    variant="outlined"
                />
            )}
            {task.due_date && (
                <Chip
                    icon={<CalendarIcon fontSize="small" />}
                    label={formatDateOnly(task.due_date)}
                    size="small"
                    variant="outlined"
                    color={task.status !== "done" && new Date(`${task.due_date}T23:59:59`) < new Date() ? "warning" : "default"}
                />
            )}
        </Stack>
    );
}

function TaskBoardCard({
    task,
    selected,
    onSelect,
    onDragStart,
    onDropBefore,
}: {
    task: ProjectTask;
    selected: boolean;
    onSelect: () => void;
    onDragStart: () => void;
    onDropBefore: () => void;
}) {
    return (
        <Paper
            draggable
            onClick={onSelect}
            onDragStart={(event) => {
                event.dataTransfer.setData("text/plain", task.id);
                event.dataTransfer.effectAllowed = "move";
                onDragStart();
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onDropBefore();
            }}
            sx={(theme) => ({
                p: 1.75,
                borderRadius: 3,
                cursor: "grab",
                border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
                backgroundColor: selected
                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.08)
                    : theme.palette.background.paper,
                boxShadow: selected
                    ? `0 0 0 1px ${alpha(theme.palette.primary.main, 0.25)}`
                    : "none",
            })}
        >
            <Stack spacing={1.25}>
                <Stack direction="row" justifyContent="space-between" spacing={1}>
                    <Typography variant="subtitle2">{task.title}</Typography>
                    <DragIndicatorIcon fontSize="small" color="action" />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                    {task.description || "No task notes yet."}
                </Typography>
                <TaskMetaChips task={task} />
            </Stack>
        </Paper>
    );
}

function TaskListCard({
    task,
    selected,
    onSelect,
}: {
    task: ProjectTask;
    selected: boolean;
    onSelect: () => void;
}) {
    return (
        <Paper
            onClick={onSelect}
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                cursor: "pointer",
                border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
                backgroundColor: selected
                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.06)
                    : theme.palette.background.paper,
            })}
        >
            <Stack spacing={1.25}>
                <Stack
                    direction={{ xs: "column", md: "row" }}
                    justifyContent="space-between"
                    spacing={1}
                >
                    <Box>
                        <Typography variant="subtitle1">{task.title}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {task.description || "No task notes yet."}
                        </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                        Updated {formatDateTime(task.updated_at)}
                    </Typography>
                </Stack>
                <TaskMetaChips task={task} />
            </Stack>
        </Paper>
    );
}

export default function ProjectDetailPage() {
    const { projectId = "" } = useParams();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [taskView, setTaskView] = useState<TaskView>("board");
    const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
    const [taskDraft, setTaskDraft] = useState<TaskDraft>(EMPTY_TASK_DRAFT);
    const [taskError, setTaskError] = useState("");
    const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null);

    const { data: project, isLoading: projectLoading, error: projectError } = useQuery({
        queryKey: ["project", projectId],
        queryFn: () => getProject(projectId),
        enabled: Boolean(projectId),
    });
    const { data: tasks, isLoading: tasksLoading, error: tasksError } = useQuery({
        queryKey: ["project", projectId, "tasks"],
        queryFn: () => listProjectTasks(projectId),
        enabled: Boolean(projectId),
    });
    const { data: users } = useQuery({
        queryKey: ["users", "directory"],
        queryFn: listUserDirectory,
    });

    const orderedTasks = sortTasks(tasks ?? []);
    const selectedTask = orderedTasks.find((task) => task.id === selectedTaskId) ?? null;
    const totalTasks = orderedTasks.length;
    const doneTasks = orderedTasks.filter((task) => task.status === "done").length;
    const inFlightTasks = orderedTasks.filter((task) => ["todo", "in_progress", "review"].includes(task.status)).length;
    const overdueTasks = orderedTasks.filter(
        (task) => task.status !== "done" && task.due_date && new Date(`${task.due_date}T23:59:59`) < new Date()
    ).length;

    const createTaskMutation = useMutation({
        mutationFn: () =>
            createProjectTask(projectId, {
                title: taskDraft.title.trim(),
                description: taskDraft.description.trim() || undefined,
                status: taskDraft.status,
                priority: taskDraft.priority,
                due_date: taskDraft.due_date || null,
                assignee_id: taskDraft.assignee_id || null,
            }),
        onSuccess: (task) => {
            queryClient.setQueryData<ProjectTask[]>(["project", projectId, "tasks"], (current) =>
                sortTasks([...(current ?? []), task])
            );
            setTaskDraft(EMPTY_TASK_DRAFT);
            setSelectedTaskId(null);
            setTaskError("");
            void queryClient.invalidateQueries({ queryKey: ["projects"] });
            showToast({ message: "Task created.", severity: "success" });
        },
        onError: (error) => {
            setTaskError(error instanceof Error ? error.message : "Failed to create task.");
        },
    });

    const updateTaskMutation = useMutation({
        mutationFn: () =>
            updateProjectTask(projectId, selectedTaskId ?? "", {
                title: taskDraft.title.trim(),
                description: taskDraft.description.trim() || null,
                status: taskDraft.status,
                priority: taskDraft.priority,
                due_date: taskDraft.due_date || null,
                assignee_id: taskDraft.assignee_id || null,
            }),
        onSuccess: (task) => {
            queryClient.setQueryData<ProjectTask[]>(["project", projectId, "tasks"], (current) =>
                sortTasks((current ?? []).map((item) => (item.id === task.id ? task : item)))
            );
            setSelectedTaskId(task.id);
            setTaskDraft(taskToDraft(task));
            setTaskError("");
            showToast({ message: "Task updated.", severity: "success" });
        },
        onError: (error) => {
            setTaskError(error instanceof Error ? error.message : "Failed to update task.");
        },
    });

    const deleteTaskMutation = useMutation({
        mutationFn: () => deleteProjectTask(projectId, selectedTaskId ?? ""),
        onSuccess: () => {
            queryClient.setQueryData<ProjectTask[]>(["project", projectId, "tasks"], (current) =>
                (current ?? []).filter((task) => task.id !== selectedTaskId)
            );
            setSelectedTaskId(null);
            setTaskDraft(EMPTY_TASK_DRAFT);
            setTaskError("");
            showToast({ message: "Task deleted.", severity: "success" });
        },
        onError: (error) => {
            setTaskError(error instanceof Error ? error.message : "Failed to delete task.");
        },
    });

    const reorderTaskMutation = useMutation({
        mutationFn: (payload: {
            columns: Array<{ status: ProjectTaskStatus; task_ids: string[] }>;
        }) => reorderProjectTasks(projectId, payload),
        onSuccess: (updatedTasks) => {
            queryClient.setQueryData(["project", projectId, "tasks"], sortTasks(updatedTasks));
        },
        onError: () => {
            void queryClient.invalidateQueries({ queryKey: ["project", projectId, "tasks"] });
            showToast({ message: "Failed to reorder tasks.", severity: "error" });
        },
    });

    function resetTaskEditor() {
        setSelectedTaskId(null);
        setTaskDraft(EMPTY_TASK_DRAFT);
        setTaskError("");
    }

    function selectTask(task: ProjectTask) {
        setSelectedTaskId(task.id);
        setTaskDraft(taskToDraft(task));
        setTaskError("");
    }

    function submitTask() {
        if (taskDraft.title.trim().length < 2) {
            setTaskError("Task title must be at least 2 characters.");
            return;
        }

        if (selectedTaskId) {
            updateTaskMutation.mutate();
            return;
        }

        createTaskMutation.mutate();
    }

    function handleDrop(targetStatus: ProjectTaskStatus, beforeTaskId?: string) {
        if (!draggingTaskId || !tasks || reorderTaskMutation.isPending) {
            return;
        }
        if (beforeTaskId === draggingTaskId) {
            setDraggingTaskId(null);
            return;
        }

        const draggingTask = tasks.find((task) => task.id === draggingTaskId);
        if (!draggingTask) {
            return;
        }

        const byStatus = Object.fromEntries(
            TASK_STATUS_OPTIONS.map((option) => [option.value, [] as ProjectTask[]])
        ) as Record<ProjectTaskStatus, ProjectTask[]>;

        tasks.forEach((task) => {
            if (task.id !== draggingTaskId) {
                byStatus[task.status].push(task);
            }
        });

        const movedTask = { ...draggingTask, status: targetStatus };
        const targetTasks = byStatus[targetStatus];
        const insertionIndex =
            beforeTaskId ? targetTasks.findIndex((task) => task.id === beforeTaskId) : -1;

        if (insertionIndex >= 0) {
            targetTasks.splice(insertionIndex, 0, movedTask);
        } else {
            targetTasks.push(movedTask);
        }

        const nextTasks = sortTasks(
            TASK_STATUS_OPTIONS.flatMap((option) =>
                byStatus[option.value].map((task, index) => ({
                    ...task,
                    status: option.value,
                    position: index,
                }))
            )
        );

        queryClient.setQueryData(["project", projectId, "tasks"], nextTasks);
        reorderTaskMutation.mutate({
            columns: TASK_STATUS_OPTIONS.map((option) => ({
                status: option.value,
                task_ids: nextTasks
                    .filter((task) => task.status === option.value)
                    .sort((left, right) => left.position - right.position)
                    .map((task) => task.id),
            })),
        });
        setDraggingTaskId(null);
    }

    if (projectLoading || tasksLoading) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={360} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!project) {
        return (
            <PageShell maxWidth="xl">
                <Alert severity="error">
                    {projectError instanceof Error ? projectError.message : "Project not found."}
                </Alert>
            </PageShell>
        );
    }

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Project workspace"
                title={project.name}
                description={
                    project.description ||
                    "Add tasks, assign work, and move cards across the delivery board."
                }
                actions={
                    <Button
                        variant="outlined"
                        startIcon={<ArrowBackIcon />}
                        onClick={() => navigate("/projects")}
                    >
                        Back to projects
                    </Button>
                }
                meta={
                    <>
                        <Chip label={`Created ${formatDate(project.created_at)}`} variant="outlined" />
                        <Chip label={`${totalTasks} tasks`} variant="outlined" />
                        <Chip
                            label={overdueTasks > 0 ? `${overdueTasks} overdue` : "No overdue work"}
                            color={overdueTasks > 0 ? "warning" : "default"}
                            variant="outlined"
                        />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        xl: "repeat(4, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label="Total tasks"
                    value={totalTasks}
                    description="All tracked work items inside this project"
                    icon={<TaskIcon />}
                />
                <StatCard
                    label="In flight"
                    value={inFlightTasks}
                    description="Tasks currently being worked, reviewed, or queued next"
                    icon={<BoardIcon />}
                    color="warning"
                />
                <StatCard
                    label="Completed"
                    value={doneTasks}
                    description="Tasks already moved to done"
                    icon={<DoneIcon />}
                    color="success"
                />
                <StatCard
                    label="Overdue"
                    value={overdueTasks}
                    description="Open tasks with a due date already behind today"
                    icon={<CalendarIcon />}
                    color={overdueTasks > 0 ? "error" : "secondary"}
                />
            </Box>

            {(projectError || tasksError) && (
                <Alert severity="error">
                    {projectError instanceof Error
                        ? projectError.message
                        : tasksError instanceof Error
                            ? tasksError.message
                            : "Failed to load project workspace."}
                </Alert>
            )}

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "360px minmax(0, 1fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard
                    title={selectedTask ? "Edit task" : "Create task"}
                    description={
                        selectedTask
                            ? "Update task details, assignee, due date, or status."
                            : "Add the next task and place it directly into the workflow."
                    }
                    action={
                        selectedTask ? (
                            <Button variant="text" onClick={resetTaskEditor}>
                                New task
                            </Button>
                        ) : undefined
                    }
                >
                    <Stack spacing={2}>
                        <TextField
                            label="Title"
                            value={taskDraft.title}
                            onChange={(event) =>
                                setTaskDraft((current) => ({ ...current, title: event.target.value }))
                            }
                            fullWidth
                        />
                        <TextField
                            label="Description"
                            value={taskDraft.description}
                            onChange={(event) =>
                                setTaskDraft((current) => ({ ...current, description: event.target.value }))
                            }
                            fullWidth
                            multiline
                            minRows={4}
                        />
                        <TextField
                            label="Status"
                            select
                            value={taskDraft.status}
                            onChange={(event) =>
                                setTaskDraft((current) => ({
                                    ...current,
                                    status: event.target.value as ProjectTaskStatus,
                                }))
                            }
                            fullWidth
                        >
                            {TASK_STATUS_OPTIONS.map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Priority"
                            select
                            value={taskDraft.priority}
                            onChange={(event) =>
                                setTaskDraft((current) => ({
                                    ...current,
                                    priority: event.target.value as ProjectTaskPriority,
                                }))
                            }
                            fullWidth
                        >
                            {TASK_PRIORITY_OPTIONS.map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Due date"
                            type="date"
                            value={taskDraft.due_date}
                            onChange={(event) =>
                                setTaskDraft((current) => ({ ...current, due_date: event.target.value }))
                            }
                            fullWidth
                            InputLabelProps={{ shrink: true }}
                        />
                        <TextField
                            label="Assignee"
                            select
                            value={taskDraft.assignee_id}
                            onChange={(event) =>
                                setTaskDraft((current) => ({ ...current, assignee_id: event.target.value }))
                            }
                            fullWidth
                        >
                            <MenuItem value="">Unassigned</MenuItem>
                            {(users ?? []).map((user) => (
                                <MenuItem key={user.id} value={user.id}>
                                    {user.full_name || user.email}
                                </MenuItem>
                            ))}
                        </TextField>

                        {selectedTask && (
                            <Alert severity="info">
                                Created {formatDateTime(selectedTask.created_at)}. Last updated{" "}
                                {formatDateTime(selectedTask.updated_at)}.
                            </Alert>
                        )}

                        {taskError && <Alert severity="error">{taskError}</Alert>}

                        <Stack direction="row" spacing={1.25}>
                            <Button
                                variant="contained"
                                onClick={submitTask}
                                disabled={createTaskMutation.isPending || updateTaskMutation.isPending}
                                fullWidth
                            >
                                {selectedTask
                                    ? updateTaskMutation.isPending
                                        ? "Saving..."
                                        : "Save task"
                                    : createTaskMutation.isPending
                                        ? "Creating..."
                                        : "Create task"}
                            </Button>
                            {selectedTask && (
                                <Button
                                    color="error"
                                    variant="outlined"
                                    onClick={() => deleteTaskMutation.mutate()}
                                    disabled={deleteTaskMutation.isPending}
                                    startIcon={<DeleteIcon />}
                                >
                                    {deleteTaskMutation.isPending ? "Deleting..." : "Delete"}
                                </Button>
                            )}
                        </Stack>
                    </Stack>
                </SectionCard>

                <SectionCard
                    title="Project flow"
                    description="Switch between a sortable Kanban board and a detailed list view."
                    action={
                        <Tabs
                            value={taskView}
                            onChange={(_, value: TaskView) => setTaskView(value)}
                            sx={{ minHeight: "auto" }}
                        >
                            <Tab
                                value="board"
                                icon={<BoardIcon fontSize="small" />}
                                iconPosition="start"
                                label="Board"
                            />
                            <Tab
                                value="list"
                                icon={<ListIcon fontSize="small" />}
                                iconPosition="start"
                                label="List"
                            />
                        </Tabs>
                    }
                >
                    {orderedTasks.length === 0 ? (
                        <EmptyState
                            icon={<TaskIcon />}
                            title="No tasks yet"
                            description="Create the first task to turn this project into an active delivery flow."
                        />
                    ) : taskView === "board" ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    md: "repeat(2, minmax(0, 1fr))",
                                    xl: "repeat(5, minmax(0, 1fr))",
                                },
                            }}
                        >
                            {TASK_STATUS_OPTIONS.map((statusOption) => {
                                const columnTasks = orderedTasks.filter(
                                    (task) => task.status === statusOption.value
                                );
                                return (
                                    <Box
                                        key={statusOption.value}
                                        onDragOver={(event) => event.preventDefault()}
                                        onDrop={(event) => {
                                            event.preventDefault();
                                            handleDrop(statusOption.value);
                                        }}
                                        sx={(theme) => ({
                                            minHeight: 240,
                                            p: 1.25,
                                            borderRadius: 4,
                                            border: `1px solid ${theme.palette.divider}`,
                                            backgroundColor: alpha(
                                                theme.palette.background.paper,
                                                theme.palette.mode === "dark" ? 0.82 : 0.72
                                            ),
                                        })}
                                    >
                                        <Stack spacing={1.25}>
                                            <Stack
                                                direction="row"
                                                justifyContent="space-between"
                                                alignItems="center"
                                            >
                                                <Typography variant="subtitle2">
                                                    {statusOption.label}
                                                </Typography>
                                                <Chip
                                                    label={columnTasks.length}
                                                    size="small"
                                                    variant="outlined"
                                                />
                                            </Stack>
                                            <Divider />
                                            <Stack spacing={1}>
                                                {columnTasks.length > 0 ? (
                                                    columnTasks.map((task) => (
                                                        <TaskBoardCard
                                                            key={task.id}
                                                            task={task}
                                                            selected={task.id === selectedTaskId}
                                                            onSelect={() => selectTask(task)}
                                                            onDragStart={() => setDraggingTaskId(task.id)}
                                                            onDropBefore={() =>
                                                                handleDrop(statusOption.value, task.id)
                                                            }
                                                        />
                                                    ))
                                                ) : (
                                                    <Box
                                                        sx={(theme) => ({
                                                            p: 2,
                                                            borderRadius: 3,
                                                            border: `1px dashed ${theme.palette.divider}`,
                                                            textAlign: "center",
                                                            color: "text.secondary",
                                                        })}
                                                    >
                                                        <Typography variant="body2">
                                                            Drop tasks here
                                                        </Typography>
                                                    </Box>
                                                )}
                                            </Stack>
                                        </Stack>
                                    </Box>
                                );
                            })}
                        </Box>
                    ) : (
                        <Stack spacing={1.5}>
                            {orderedTasks.map((task) => (
                                <TaskListCard
                                    key={task.id}
                                    task={task}
                                    selected={task.id === selectedTaskId}
                                    onSelect={() => selectTask(task)}
                                />
                            ))}
                        </Stack>
                    )}
                </SectionCard>
            </Box>
        </PageShell>
    );
}
