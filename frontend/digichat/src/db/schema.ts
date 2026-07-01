import {
  pgTable,
  text,
  timestamp,
  uuid,
  uniqueIndex,
  index,
  integer,
  jsonb,
} from "drizzle-orm/pg-core";

export const tenants = pgTable("tenants", {
  id: uuid("id").defaultRandom().primaryKey(),
  slug: text("slug").notNull().unique(),
  name: text("name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const userTenants = pgTable(
  "user_tenants",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    providerAccountId: text("provider_account_id").notNull(),
    tenantId: uuid("tenant_id")
      .references(() => tenants.id, { onDelete: "cascade" })
      .notNull(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (t) => [uniqueIndex("user_tenants_provider_tenant").on(t.providerAccountId, t.tenantId)]
);

export const apiKeys = pgTable("api_keys", {
  id: uuid("id").defaultRandom().primaryKey(),
  tenantId: uuid("tenant_id")
    .references(() => tenants.id, { onDelete: "cascade" })
    .notNull(),
  keyHash: text("key_hash").notNull(),
  keyPrefix: text("key_prefix").notNull(),
  label: text("label"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const conversations = pgTable(
  "conversations",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    tenantId: uuid("tenant_id")
      .references(() => tenants.id, { onDelete: "cascade" })
      .notNull(),
    ownerUserSub: text("owner_user_sub").notNull(),
    title: text("title").notNull().default("New chat"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (t) => [
    index("conversations_tenant_owner_updated").on(
      t.tenantId,
      t.ownerUserSub,
      t.updatedAt
    ),
  ]
);

/** Saved DigiQuant backtest rows for comparison (DigiClone). */
export const quantRuns = pgTable(
  "quant_runs",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    conversationId: uuid("conversation_id")
      .references(() => conversations.id, { onDelete: "cascade" })
      .notNull(),
    label: text("label").notNull().default("Backtest"),
    strategyName: text("strategy_name").notNull(),
    symbols: jsonb("symbols").notNull().$type<string[]>(),
    strategyParams: jsonb("strategy_params").$type<Record<string, unknown>>(),
    backtestResult: jsonb("backtest_result").notNull().$type<Record<string, unknown>>(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (t) => [
    index("quant_runs_conversation_created").on(t.conversationId, t.createdAt),
  ]
);

export const conversationMessages = pgTable(
  "conversation_messages",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    conversationId: uuid("conversation_id")
      .references(() => conversations.id, { onDelete: "cascade" })
      .notNull(),
    sequence: integer("sequence").notNull(),
    /** Full AI SDK UI message (`id`, `role`, `parts`, ...). */
    payload: jsonb("payload").notNull().$type<Record<string, unknown>>(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (t) => [uniqueIndex("conversation_messages_conv_seq").on(t.conversationId, t.sequence)]
);

export type Tenant = typeof tenants.$inferSelect;
export type ApiKeyRow = typeof apiKeys.$inferSelect;
export type ConversationRow = typeof conversations.$inferSelect;
export type ConversationMessageRow = typeof conversationMessages.$inferSelect;
export type QuantRunRow = typeof quantRuns.$inferSelect;
