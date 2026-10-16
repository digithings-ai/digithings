CREATE TABLE "quant_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"conversation_id" uuid NOT NULL,
	"label" text DEFAULT 'Backtest' NOT NULL,
	"strategy_name" text NOT NULL,
	"symbols" jsonb NOT NULL,
	"strategy_params" jsonb,
	"backtest_result" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "quant_runs" ADD CONSTRAINT "quant_runs_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "quant_runs_conversation_created" ON "quant_runs" USING btree ("conversation_id","created_at");
