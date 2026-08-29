export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      auction_quotes: {
        Row: {
          approved: number | null
          auction_id: string
          call_id: string | null
          carrier_id: string
          carrier_name: string | null
          created_at: string | null
          final_ask: number | null
          id: number
          quote_ms: number | null
          reason: string
          rounds: number
          winner: boolean
        }
        Insert: {
          approved?: number | null
          auction_id: string
          call_id?: string | null
          carrier_id: string
          carrier_name?: string | null
          created_at?: string | null
          final_ask?: number | null
          id?: number
          quote_ms?: number | null
          reason: string
          rounds?: number
          winner?: boolean
        }
        Update: {
          approved?: number | null
          auction_id?: string
          call_id?: string | null
          carrier_id?: string
          carrier_name?: string | null
          created_at?: string | null
          final_ask?: number | null
          id?: number
          quote_ms?: number | null
          reason?: string
          rounds?: number
          winner?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "auction_quotes_auction_id_fkey"
            columns: ["auction_id"]
            isOneToOne: false
            referencedRelation: "auctions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "auction_quotes_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
      auctions: {
        Row: {
          admission_warnings: Json | null
          created_at: string
          decided_at: string | null
          decision_reason: string | null
          dial_plan: Json | null
          hard_deadline_s: number | null
          id: string
          legs_budget: number | null
          legs_planned: number | null
          mandate_id: string | null
          opened_at: string | null
          operation_id: string
          release_reason: string | null
          released_from: string | null
          reserve_amount: number | null
          reserve_attempts: number
          reserved_at: string | null
          reserved_by: string | null
          settled_at: string | null
          soft_deadline_s: number | null
          started_at: string | null
          state: Database["public"]["Enums"]["auction_state"]
          status: string
          winner_call_id: string | null
        }
        Insert: {
          admission_warnings?: Json | null
          created_at?: string
          decided_at?: string | null
          decision_reason?: string | null
          dial_plan?: Json | null
          hard_deadline_s?: number | null
          id?: string
          legs_budget?: number | null
          legs_planned?: number | null
          mandate_id?: string | null
          opened_at?: string | null
          operation_id: string
          release_reason?: string | null
          released_from?: string | null
          reserve_amount?: number | null
          reserve_attempts?: number
          reserved_at?: string | null
          reserved_by?: string | null
          settled_at?: string | null
          soft_deadline_s?: number | null
          started_at?: string | null
          state?: Database["public"]["Enums"]["auction_state"]
          status?: string
          winner_call_id?: string | null
        }
        Update: {
          admission_warnings?: Json | null
          created_at?: string
          decided_at?: string | null
          decision_reason?: string | null
          dial_plan?: Json | null
          hard_deadline_s?: number | null
          id?: string
          legs_budget?: number | null
          legs_planned?: number | null
          mandate_id?: string | null
          opened_at?: string | null
          operation_id?: string
          release_reason?: string | null
          released_from?: string | null
          reserve_amount?: number | null
          reserve_attempts?: number
          reserved_at?: string | null
          reserved_by?: string | null
          settled_at?: string | null
          soft_deadline_s?: number | null
          started_at?: string | null
          state?: Database["public"]["Enums"]["auction_state"]
          status?: string
          winner_call_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "auctions_mandate_id_fkey"
            columns: ["mandate_id"]
            isOneToOne: false
            referencedRelation: "mandates"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "auctions_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "auctions_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "auctions_winner_call_fk"
            columns: ["winner_call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
      call_briefs: {
        Row: {
          actions: Json
          call_id: string
          created_at: string | null
          mentions: Json
          outcome: string | null
          recap_sent_at: string | null
          recap_sent_to: string | null
        }
        Insert: {
          actions?: Json
          call_id: string
          created_at?: string | null
          mentions?: Json
          outcome?: string | null
          recap_sent_at?: string | null
          recap_sent_to?: string | null
        }
        Update: {
          actions?: Json
          call_id?: string
          created_at?: string | null
          mentions?: Json
          outcome?: string | null
          recap_sent_at?: string | null
          recap_sent_to?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "call_briefs_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: true
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
      calls: {
        Row: {
          answered_at: string | null
          auction_id: string | null
          audio_public_url: string | null
          call_sid: string | null
          carrier_id: string | null
          carrier_name: string | null
          carrier_phone: string | null
          conference_name: string | null
          created_at: string
          dial_attempt: number | null
          dial_error: string | null
          direction: string
          ended_at: string | null
          final_ask: number | null
          id: string
          is_winner: boolean
          language: string | null
          leg_role: string | null
          operation_id: string | null
          outcome_reason: string | null
          phone: string | null
          recording_url: string | null
          released_at: string | null
          rounds: number
          started_at: string | null
          status: Database["public"]["Enums"]["call_status"]
          transcript: Json | null
          transcript_words: number | null
        }
        Insert: {
          answered_at?: string | null
          auction_id?: string | null
          audio_public_url?: string | null
          call_sid?: string | null
          carrier_id?: string | null
          carrier_name?: string | null
          carrier_phone?: string | null
          conference_name?: string | null
          created_at?: string
          dial_attempt?: number | null
          dial_error?: string | null
          direction?: string
          ended_at?: string | null
          final_ask?: number | null
          id?: string
          is_winner?: boolean
          language?: string | null
          leg_role?: string | null
          operation_id?: string | null
          outcome_reason?: string | null
          phone?: string | null
          recording_url?: string | null
          released_at?: string | null
          rounds?: number
          started_at?: string | null
          status?: Database["public"]["Enums"]["call_status"]
          transcript?: Json | null
          transcript_words?: number | null
        }
        Update: {
          answered_at?: string | null
          auction_id?: string | null
          audio_public_url?: string | null
          call_sid?: string | null
          carrier_id?: string | null
          carrier_name?: string | null
          carrier_phone?: string | null
          conference_name?: string | null
          created_at?: string
          dial_attempt?: number | null
          dial_error?: string | null
          direction?: string
          ended_at?: string | null
          final_ask?: number | null
          id?: string
          is_winner?: boolean
          language?: string | null
          leg_role?: string | null
          operation_id?: string | null
          outcome_reason?: string | null
          phone?: string | null
          recording_url?: string | null
          released_at?: string | null
          rounds?: number
          started_at?: string | null
          status?: Database["public"]["Enums"]["call_status"]
          transcript?: Json | null
          transcript_words?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "calls_auction_id_fkey"
            columns: ["auction_id"]
            isOneToOne: false
            referencedRelation: "auctions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "calls_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "calls_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      commitments: {
        Row: {
          affirmation_quote: string | null
          affirmation_t_end_ms: number | null
          affirmation_t_start_ms: number | null
          anchor_confidence: number | null
          anchor_method: string | null
          anchor_state: string
          audio_url: string | null
          call_id: string
          confidence: number | null
          confirmed_at: string | null
          created_at: string
          field: string
          id: string
          mandate_hash: string | null
          negotiation_round: number | null
          operation_id: string | null
          quote: string | null
          read_back_at: string | null
          read_back_token: string | null
          state: Database["public"]["Enums"]["commitment_state"]
          supersedes: string | null
          t_end_ms: number | null
          t_start_ms: number | null
          value: string
        }
        Insert: {
          affirmation_quote?: string | null
          affirmation_t_end_ms?: number | null
          affirmation_t_start_ms?: number | null
          anchor_confidence?: number | null
          anchor_method?: string | null
          anchor_state?: string
          audio_url?: string | null
          call_id: string
          confidence?: number | null
          confirmed_at?: string | null
          created_at?: string
          field: string
          id?: string
          mandate_hash?: string | null
          negotiation_round?: number | null
          operation_id?: string | null
          quote?: string | null
          read_back_at?: string | null
          read_back_token?: string | null
          state?: Database["public"]["Enums"]["commitment_state"]
          supersedes?: string | null
          t_end_ms?: number | null
          t_start_ms?: number | null
          value: string
        }
        Update: {
          affirmation_quote?: string | null
          affirmation_t_end_ms?: number | null
          affirmation_t_start_ms?: number | null
          anchor_confidence?: number | null
          anchor_method?: string | null
          anchor_state?: string
          audio_url?: string | null
          call_id?: string
          confidence?: number | null
          confirmed_at?: string | null
          created_at?: string
          field?: string
          id?: string
          mandate_hash?: string | null
          negotiation_round?: number | null
          operation_id?: string | null
          quote?: string | null
          read_back_at?: string | null
          read_back_token?: string | null
          state?: Database["public"]["Enums"]["commitment_state"]
          supersedes?: string | null
          t_end_ms?: number | null
          t_start_ms?: number | null
          value?: string
        }
        Relationships: [
          {
            foreignKeyName: "commitments_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commitments_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commitments_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "commitments_supersedes_fkey"
            columns: ["supersedes"]
            isOneToOne: false
            referencedRelation: "commitments"
            referencedColumns: ["id"]
          },
        ]
      }
      dossiers: {
        Row: {
          commitments: Json
          comparison: Json
          created_at: string | null
          escalations: Json
          financial: Json
          headline: string | null
          mandate_hash: string | null
          operation_id: string
          operational: Json
          outcome: string
          timeline: Json
        }
        Insert: {
          commitments?: Json
          comparison?: Json
          created_at?: string | null
          escalations?: Json
          financial?: Json
          headline?: string | null
          mandate_hash?: string | null
          operation_id: string
          operational?: Json
          outcome: string
          timeline?: Json
        }
        Update: {
          commitments?: Json
          comparison?: Json
          created_at?: string | null
          escalations?: Json
          financial?: Json
          headline?: string | null
          mandate_hash?: string | null
          operation_id?: string
          operational?: Json
          outcome?: string
          timeline?: Json
        }
        Relationships: [
          {
            foreignKeyName: "dossiers_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: true
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dossiers_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: true
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      escalations: {
        Row: {
          brief: string
          call_id: string
          computation: Json
          created_at: string
          human_joined_at: string | null
          human_phone: string | null
          id: string
          resolution: string | null
          state: Database["public"]["Enums"]["escalation_state"]
          trigger: string | null
        }
        Insert: {
          brief: string
          call_id: string
          computation?: Json
          created_at?: string
          human_joined_at?: string | null
          human_phone?: string | null
          id?: string
          resolution?: string | null
          state?: Database["public"]["Enums"]["escalation_state"]
          trigger?: string | null
        }
        Update: {
          brief?: string
          call_id?: string
          computation?: Json
          created_at?: string
          human_joined_at?: string | null
          human_phone?: string | null
          id?: string
          resolution?: string | null
          state?: Database["public"]["Enums"]["escalation_state"]
          trigger?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "escalations_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
      mandates: {
        Row: {
          break_even_rate: number | null
          canonical: Json | null
          created_at: string
          currency: string
          escalation_band: Json | null
          escalation_triggers: Json | null
          id: string
          issue_warnings: Json | null
          issued_at: string | null
          ladder: Json | null
          mandate_hash: string | null
          max_amount: number | null
          max_rate: number | null
          max_rounds: number
          may_reveal_best_price: boolean
          may_reveal_competitor_name: boolean
          may_reveal_max_rate: boolean
          min_rate: number
          operation_id: string
          pickup_from: string | null
          pickup_to: string | null
          pickup_window_end: string | null
          pickup_window_start: string | null
          target_amount: number | null
          target_rate: number | null
        }
        Insert: {
          break_even_rate?: number | null
          canonical?: Json | null
          created_at?: string
          currency?: string
          escalation_band?: Json | null
          escalation_triggers?: Json | null
          id?: string
          issue_warnings?: Json | null
          issued_at?: string | null
          ladder?: Json | null
          mandate_hash?: string | null
          max_amount?: number | null
          max_rate?: number | null
          max_rounds?: number
          may_reveal_best_price?: boolean
          may_reveal_competitor_name?: boolean
          may_reveal_max_rate?: boolean
          min_rate?: number
          operation_id: string
          pickup_from?: string | null
          pickup_to?: string | null
          pickup_window_end?: string | null
          pickup_window_start?: string | null
          target_amount?: number | null
          target_rate?: number | null
        }
        Update: {
          break_even_rate?: number | null
          canonical?: Json | null
          created_at?: string
          currency?: string
          escalation_band?: Json | null
          escalation_triggers?: Json | null
          id?: string
          issue_warnings?: Json | null
          issued_at?: string | null
          ladder?: Json | null
          mandate_hash?: string | null
          max_amount?: number | null
          max_rate?: number | null
          max_rounds?: number
          may_reveal_best_price?: boolean
          may_reveal_competitor_name?: boolean
          may_reveal_max_rate?: boolean
          min_rate?: number
          operation_id?: string
          pickup_from?: string | null
          pickup_to?: string | null
          pickup_window_end?: string | null
          pickup_window_start?: string | null
          target_amount?: number | null
          target_rate?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "mandates_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "mandates_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      operations: {
        Row: {
          cargo_value_usd: number | null
          clock_state: Database["public"]["Enums"]["clock_state"]
          clock_state_since: string
          closed_at: string | null
          container: string | null
          created_at: string
          currency: string
          demurrage_per_day: number
          destination: string | null
          free_time_ends: string
          id: string
          idempotency_key: string | null
          origin: string | null
          outcome: string | null
          phase: Database["public"]["Enums"]["phase_key"]
          phase_since: string
          ref: string
          source_event: Json | null
          status: string
        }
        Insert: {
          cargo_value_usd?: number | null
          clock_state?: Database["public"]["Enums"]["clock_state"]
          clock_state_since?: string
          closed_at?: string | null
          container?: string | null
          created_at?: string
          currency?: string
          demurrage_per_day?: number
          destination?: string | null
          free_time_ends: string
          id?: string
          idempotency_key?: string | null
          origin?: string | null
          outcome?: string | null
          phase?: Database["public"]["Enums"]["phase_key"]
          phase_since?: string
          ref: string
          source_event?: Json | null
          status?: string
        }
        Update: {
          cargo_value_usd?: number | null
          clock_state?: Database["public"]["Enums"]["clock_state"]
          clock_state_since?: string
          closed_at?: string | null
          container?: string | null
          created_at?: string
          currency?: string
          demurrage_per_day?: number
          destination?: string | null
          free_time_ends?: string
          id?: string
          idempotency_key?: string | null
          origin?: string | null
          outcome?: string | null
          phase?: Database["public"]["Enums"]["phase_key"]
          phase_since?: string
          ref?: string
          source_event?: Json | null
          status?: string
        }
        Relationships: []
      }
      phase_events: {
        Row: {
          auction_id: string | null
          call_id: string | null
          created_at: string | null
          detail: string | null
          id: number
          kind: string
          ms_in_previous: number | null
          operation_id: string
          payload: Json | null
          phase: Database["public"]["Enums"]["phase_key"]
          previous: Database["public"]["Enums"]["phase_key"] | null
          trigger: string
        }
        Insert: {
          auction_id?: string | null
          call_id?: string | null
          created_at?: string | null
          detail?: string | null
          id?: number
          kind: string
          ms_in_previous?: number | null
          operation_id: string
          payload?: Json | null
          phase: Database["public"]["Enums"]["phase_key"]
          previous?: Database["public"]["Enums"]["phase_key"] | null
          trigger: string
        }
        Update: {
          auction_id?: string | null
          call_id?: string | null
          created_at?: string | null
          detail?: string | null
          id?: number
          kind?: string
          ms_in_previous?: number | null
          operation_id?: string
          payload?: Json | null
          phase?: Database["public"]["Enums"]["phase_key"]
          previous?: Database["public"]["Enums"]["phase_key"] | null
          trigger?: string
        }
        Relationships: [
          {
            foreignKeyName: "phase_events_auction_id_fkey"
            columns: ["auction_id"]
            isOneToOne: false
            referencedRelation: "auctions"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "phase_events_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "phase_events_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "phase_events_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      policy_events: {
        Row: {
          amount: number | null
          ask: string | null
          call_id: string
          counterparty_ask: number | null
          created_at: string
          decision: Database["public"]["Enums"]["policy_decision"]
          id: string
          mandate_hash: string | null
          reason: string | null
          round: number | null
          utterance: string | null
        }
        Insert: {
          amount?: number | null
          ask?: string | null
          call_id: string
          counterparty_ask?: number | null
          created_at?: string
          decision: Database["public"]["Enums"]["policy_decision"]
          id?: string
          mandate_hash?: string | null
          reason?: string | null
          round?: number | null
          utterance?: string | null
        }
        Update: {
          amount?: number | null
          ask?: string | null
          call_id?: string
          counterparty_ask?: number | null
          created_at?: string
          decision?: Database["public"]["Enums"]["policy_decision"]
          id?: string
          mandate_hash?: string | null
          reason?: string | null
          round?: number | null
          utterance?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "policy_events_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
      read_backs: {
        Row: {
          attempt: number
          call_id: string
          created_at: string | null
          id: number
          operation_id: string
          outcome: string | null
          response_text: string | null
          slots: Json
          spoken_text: string
          t_response_ms: number | null
          t_spoken_ms: number | null
          token: string
        }
        Insert: {
          attempt?: number
          call_id: string
          created_at?: string | null
          id?: number
          operation_id: string
          outcome?: string | null
          response_text?: string | null
          slots: Json
          spoken_text: string
          t_response_ms?: number | null
          t_spoken_ms?: number | null
          token: string
        }
        Update: {
          attempt?: number
          call_id?: string
          created_at?: string | null
          id?: number
          operation_id?: string
          outcome?: string | null
          response_text?: string | null
          slots?: Json
          spoken_text?: string
          t_response_ms?: number | null
          t_spoken_ms?: number | null
          token?: string
        }
        Relationships: [
          {
            foreignKeyName: "read_backs_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "read_backs_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "read_backs_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      recap_deliveries: {
        Row: {
          body: string
          call_id: string | null
          channel: string
          created_at: string | null
          error: string | null
          id: number
          operation_id: string
          provider_id: string | null
          status: string
          subject: string | null
          target: string
        }
        Insert: {
          body: string
          call_id?: string | null
          channel: string
          created_at?: string | null
          error?: string | null
          id?: number
          operation_id: string
          provider_id?: string | null
          status?: string
          subject?: string | null
          target: string
        }
        Update: {
          body?: string
          call_id?: string | null
          channel?: string
          created_at?: string | null
          error?: string | null
          id?: number
          operation_id?: string
          provider_id?: string | null
          status?: string
          subject?: string | null
          target?: string
        }
        Relationships: [
          {
            foreignKeyName: "recap_deliveries_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "recap_deliveries_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operation_progress"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "recap_deliveries_operation_id_fkey"
            columns: ["operation_id"]
            isOneToOne: false
            referencedRelation: "operations"
            referencedColumns: ["id"]
          },
        ]
      }
      utterances: {
        Row: {
          call_id: string
          created_at: string
          id: string
          interrupted: boolean
          speaker: string
          t_end_ms: number | null
          t_ms: number | null
          t_start_ms: number | null
          text: string
        }
        Insert: {
          call_id: string
          created_at?: string
          id?: string
          interrupted?: boolean
          speaker?: string
          t_end_ms?: number | null
          t_ms?: number | null
          t_start_ms?: number | null
          text: string
        }
        Update: {
          call_id?: string
          created_at?: string
          id?: string
          interrupted?: boolean
          speaker?: string
          t_end_ms?: number | null
          t_ms?: number | null
          t_start_ms?: number | null
          text?: string
        }
        Relationships: [
          {
            foreignKeyName: "utterances_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      operation_progress: {
        Row: {
          id: string | null
          last_event_at: string | null
          on_branch: boolean | null
          phase: Database["public"]["Enums"]["phase_key"] | null
          phase_since: string | null
          ref: string | null
          spine_step: number | null
          steps_taken: number | null
        }
        Insert: {
          id?: string | null
          last_event_at?: never
          on_branch?: never
          phase?: Database["public"]["Enums"]["phase_key"] | null
          phase_since?: string | null
          ref?: string | null
          spine_step?: never
          steps_taken?: never
        }
        Update: {
          id?: string | null
          last_event_at?: never
          on_branch?: never
          phase?: Database["public"]["Enums"]["phase_key"] | null
          phase_since?: string | null
          ref?: string | null
          spine_step?: never
          steps_taken?: never
        }
        Relationships: []
      }
    }
    Functions: {
      advance_phase: {
        Args: {
          p_auction_id?: string
          p_call_id?: string
          p_detail?: string
          p_kind: string
          p_operation_id: string
          p_payload?: Json
          p_phase: Database["public"]["Enums"]["phase_key"]
          p_trigger: string
        }
        Returns: number
      }
      release_reservation: {
        Args: { p_auction_id: string; p_reason: string }
        Returns: Json
      }
      try_reserve_auction: {
        Args: {
          p_amount: number
          p_auction_id: string
          p_call_id: string
          p_reason: string
        }
        Returns: Json
      }
    }
    Enums: {
      auction_state: "pending" | "running" | "settled" | "cancelled"
      call_status:
        | "dialing"
        | "live"
        | "escalated"
        | "done"
        | "released"
        | "failed"
      clock_state: "safe" | "warning" | "critical" | "expired" | "stopped"
      commitment_state:
        | "proposed"
        | "anchored"
        | "void"
        | "read_back"
        | "confirmed"
        | "in_execution"
        | "amended"
        | "retracted"
      escalation_state: "open" | "approved" | "rejected"
      phase_key:
        | "detected"
        | "mandate_issued"
        | "market_open"
        | "negotiating"
        | "reserved"
        | "committed"
        | "verified"
        | "closed"
        | "disrupted"
        | "renegotiating"
        | "escalated"
        | "resolved"
        | "failed"
      policy_decision: "allow" | "deny" | "block" | "escalate"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      auction_state: ["pending", "running", "settled", "cancelled"],
      call_status: [
        "dialing",
        "live",
        "escalated",
        "done",
        "released",
        "failed",
      ],
      clock_state: ["safe", "warning", "critical", "expired", "stopped"],
      commitment_state: [
        "proposed",
        "anchored",
        "void",
        "read_back",
        "confirmed",
        "in_execution",
        "amended",
        "retracted",
      ],
      escalation_state: ["open", "approved", "rejected"],
      phase_key: [
        "detected",
        "mandate_issued",
        "market_open",
        "negotiating",
        "reserved",
        "committed",
        "verified",
        "closed",
        "disrupted",
        "renegotiating",
        "escalated",
        "resolved",
        "failed",
      ],
      policy_decision: ["allow", "deny", "block", "escalate"],
    },
  },
} as const
