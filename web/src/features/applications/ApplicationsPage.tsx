import type { DragEndEvent } from "@dnd-kit/core";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { GripVertical } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { ApplicationStatus, Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { Button, EmptyState, ErrorNote, Meta, SegmentedControl } from "@/components/ui";
import { useToast } from "@/components/Toaster";
import { Score } from "@/features/jobs/Score";
import { PageHeader } from "@/features/shell/AppShell";
import { useBreakpoint } from "@/lib/breakpoints";
import { formatDate, STATUS_LABELS, STATUS_ORDER } from "@/lib/format";

type CardData = Schemas["ApplicationCard"];
const SAVED_LIMIT = 12;

function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function useMoveCard() {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ jobId, status }: { jobId: number; status: ApplicationStatus }) =>
      unwrap(
        client.PATCH("/api/v1/jobs/{job_id}/application", {
          params: { path: { job_id: jobId } },
          body: { status },
        }),
      ),
    onMutate: async ({ jobId, status }) => {
      await queryClient.cancelQueries({ queryKey: keys.applications });
      const previous = queryClient.getQueryData<CardData[]>(keys.applications);
      queryClient.setQueryData<CardData[]>(keys.applications, (cards) =>
        cards?.map((card) => (card.job_id === jobId ? { ...card, status } : card)),
      );
      return { previous };
    },
    onError: (error, _, context) => {
      if (context?.previous) queryClient.setQueryData(keys.applications, context.previous);
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't move the card", description: message, reference });
    },
    onSettled: async (_, __, { jobId }) => {
      await queryClient.invalidateQueries({ queryKey: keys.applications });
      await queryClient.invalidateQueries({ queryKey: keys.job(jobId) });
      await queryClient.invalidateQueries({ queryKey: keys.jobs });
    },
  });
}

function BoardSkeleton() {
  return (
    <div role="status" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <span className="sr-only">Loading applications…</span>
      {[0, 1, 2, 3].map((index) => (
        <div key={index} aria-hidden className="h-48 animate-pulse rounded-card bg-subtle" />
      ))}
    </div>
  );
}

export function ApplicationsPage() {
  const cards = useQuery({
    queryKey: keys.applications,
    queryFn: () => unwrap(client.GET("/api/v1/applications")),
  });
  const move = useMoveCard();
  const wide = useBreakpoint("lg");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over) return;
    const card = cards.data?.find((item) => item.job_id === active.id);
    const status = over.id as ApplicationStatus;
    if (card && card.status !== status) move.mutate({ jobId: card.job_id, status });
  };
  const onMove = (jobId: number, status: ApplicationStatus) => move.mutate({ jobId, status });
  const inStatus = (status: ApplicationStatus) =>
    (cards.data ?? [])
      .filter((card) => card.status === status)
      .sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1));

  return (
    <>
      <PageHeader
        title="Applications"
        description={
          wide
            ? "Drag a card to update its status, or use the menu on each card."
            : "Pick a stage, then move a card with its menu."
        }
      />
      {cards.isPending && <BoardSkeleton />}
      {cards.isError && <ErrorNote {...describeError(cards.error)} />}
      {cards.isSuccess && cards.data.length === 0 && (
        <EmptyState title="Nothing to track yet">
          Jobs you save show up here so you can follow each application.
        </EmptyState>
      )}
      {cards.isSuccess &&
        cards.data.length > 0 &&
        (wide ? (
          <DndContext sensors={sensors} onDragEnd={onDragEnd}>
            <div
              data-tour="board"
              className="relative flex snap-x gap-3 overflow-x-auto pb-4 2xl:grid 2xl:grid-cols-4 2xl:overflow-visible"
            >
              {STATUS_ORDER.map((status) => (
                <Column key={status} status={status} cards={inStatus(status)} onMove={onMove} />
              ))}
            </div>
          </DndContext>
        ) : (
          <PhoneStages cards={cards.data} inStatus={inStatus} onMove={onMove} />
        ))}
    </>
  );
}

/** Below 1024 px: stage tabs (they scroll sideways inside their own row) and one column of cards. */
function PhoneStages({
  cards,
  inStatus,
  onMove,
}: {
  cards: CardData[];
  inStatus: (status: ApplicationStatus) => CardData[];
  onMove: (jobId: number, status: ApplicationStatus) => void;
}) {
  const [stage, setStage] = useState<ApplicationStatus>(
    () => STATUS_ORDER.find((status) => cards.some((card) => card.status === status)) ?? "draft",
  );
  const shown = inStatus(stage);
  return (
    <div className="flex flex-col gap-4">
      <SegmentedControl
        kind="tabs"
        label="Stage"
        value={stage}
        onChange={setStage}
        className="self-start"
        options={STATUS_ORDER.map((status) => ({
          value: status,
          tabId: `stage-${status}`,
          panelId: "stage-panel",
          label: `${STATUS_LABELS[status]} ${String(inStatus(status).length)}`,
        }))}
      />
      <div data-tour="board" role="tabpanel" id="stage-panel" aria-labelledby={`stage-${stage}`}>
        {shown.length === 0 ? (
          <EmptyState title="Nothing here yet">Cards you move to this stage show up in this list.</EmptyState>
        ) : (
          <ul className="flex max-w-2xl flex-col gap-2">
            {shown.map((card) => (
              <KanbanCard key={card.job_id} card={card} onMove={onMove} phone />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Column({
  status,
  cards,
  onMove,
}: {
  status: ApplicationStatus;
  cards: CardData[];
  onMove: (jobId: number, status: ApplicationStatus) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const [expanded, setExpanded] = useState(false);
  const limit = status === "draft" && !expanded ? SAVED_LIMIT : cards.length;
  return (
    <section
      ref={setNodeRef}
      aria-label={STATUS_LABELS[status]}
      className={clsx(
        "flex w-72 shrink-0 snap-start flex-col rounded-card p-2 transition-colors duration-(--duration-base) ease-(--ease-calm) 2xl:w-auto 2xl:min-w-0",
        isOver ? "bg-accent-soft" : "glass glass-plate",
      )}
    >
      <h2 className="flex items-center justify-between px-2 py-2 text-secondary font-semibold">
        {STATUS_LABELS[status]}
        <span className="text-caption font-medium text-muted">{cards.length}</span>
      </h2>
      <ul className="flex min-h-24 flex-col gap-2">
        {cards.slice(0, limit).map((card) => (
          <KanbanCard key={card.job_id} card={card} onMove={onMove} />
        ))}
      </ul>
      {cards.length > limit && (
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => setExpanded(true)}>
          Show {cards.length - limit} more
        </Button>
      )}
    </section>
  );
}

function KanbanCard({
  card,
  onMove,
  phone = false,
}: {
  card: CardData;
  onMove: (jobId: number, status: ApplicationStatus) => void;
  phone?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: card.job_id,
    disabled: phone,
  });
  const style = transform
    ? { transform: `translate3d(${String(transform.x)}px, ${String(transform.y)}px, 0)` }
    : undefined;
  const selectId = `status-${String(card.job_id)}`;
  return (
    <li
      ref={setNodeRef}
      style={style}
      className={clsx("glass-ctl rounded-control p-3", isDragging && "relative z-20 rotate-1 shadow-pop")}
    >
      <div className="flex items-start gap-2">
        {!phone && (
          <button
            type="button"
            className="-mt-1.5 -ml-3 inline-flex size-11 shrink-0 cursor-grab touch-none items-center justify-center rounded-full text-faint hover:bg-subtle hover:text-ink active:cursor-grabbing"
            aria-label={`Drag ${card.title}`}
            {...listeners}
            {...attributes}
          >
            <GripVertical className="size-5" aria-hidden />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <Link
            to={`/jobs/${String(card.job_id)}`}
            className={clsx(
              "block font-medium hover:text-accent",
              phone ? "text-subheading" : "line-clamp-2 text-secondary",
            )}
          >
            {card.title}
          </Link>
          <p className="truncate text-caption text-muted">{card.company || "Unknown company"}</p>
        </div>
        <Score score={card.match_score} variant="compact" />
      </div>
      {card.has_documents && (
        <p className="mt-1">
          <Meta tone="good">Documents ready</Meta>
        </p>
      )}
      {card.follow_up_at && (card.status === "submitted" || card.status === "interview") && (
        <p className="mt-1">
          <Meta tone={card.follow_up_at < today() ? "warn" : "neutral"}>
            {card.follow_up_at < today() ? "Follow-up due " : "Follow up "}
            {formatDate(card.follow_up_at)}
          </Meta>
        </p>
      )}
      {card.note && <p className="mt-2 line-clamp-2 text-caption text-muted">{card.note}</p>}
      <div className="mt-3 flex flex-col gap-1">
        <label className={phone ? "text-caption text-muted" : "sr-only"} htmlFor={selectId}>
          {phone ? "Move to…" : `Status for ${card.title}`}
        </label>
        <select
          id={selectId}
          value={card.status}
          onChange={(event) => onMove(card.job_id, event.target.value as ApplicationStatus)}
          className="h-11 w-full min-w-0 rounded-control bg-subtle px-3 text-secondary text-ink focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {STATUS_ORDER.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>
    </li>
  );
}
