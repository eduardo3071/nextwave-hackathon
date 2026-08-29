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
      auctions: {
        Row: {
          created_at: string
          id: string
          operation_id: string
          settled_at: string | null
          started_at: string | null
          state: Database["public"]["Enums"]["auction_state"]
          winner_call_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          operation_id: string
          settled_at?: string | null
          started_at?: string | null
          state?: Database["public"]["Enums"]["auction_state"]
          winner_call_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          operation_id?: string
          settled_at?: string | null
          started_at?: string | null
          state?: Database["public"]["Enums"]["auction_state"]
          winner_call_id?: string | null
        }
        Relationships: [
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
      calls: {
        Row: {
          auction_id: string
          carrier_name: string
          carrier_phone: string | null
          created_at: string
          final_ask: number | null
          id: string
          is_winner: boolean
          outcome_reason: string | null
          recording_url: string | null
          released_at: string | null
          rounds: number
          status: Database["public"]["Enums"]["call_status"]
        }
        Insert: {
          auction_id: string
          carrier_name: string
          carrier_phone?: string | null
          created_at?: string
          final_ask?: number | null
          id?: string
          is_winner?: boolean
          outcome_reason?: string | null
          recording_url?: string | null
          released_at?: string | null
          rounds?: number
          status?: Database["public"]["Enums"]["call_status"]
        }
        Update: {
          auction_id?: string
          carrier_name?: string
          carrier_phone?: string | null
          created_at?: string
          final_ask?: number | null
          id?: string
          is_winner?: boolean
          outcome_reason?: string | null
          recording_url?: string | null
          released_at?: string | null
          rounds?: number
          status?: Database["public"]["Enums"]["call_status"]
        }
        Relationships: [
          {
            foreignKeyName: "calls_auction_id_fkey"
            columns: ["auction_id"]
            isOneToOne: false
            referencedRelation: "auctions"
            referencedColumns: ["id"]
          },
        ]
      }
      commitments: {
        Row: {
          call_id: string
          created_at: string
          field: string
          id: string
          quote: string | null
          state: Database["public"]["Enums"]["commitment_state"]
          t_end_ms: number | null
          t_start_ms: number | null
          value: string
        }
        Insert: {
          call_id: string
          created_at?: string
          field: string
          id?: string
          quote?: string | null
          state?: Database["public"]["Enums"]["commitment_state"]
          t_end_ms?: number | null
          t_start_ms?: number | null
          value: string
        }
        Update: {
          call_id?: string
          created_at?: string
          field?: string
          id?: string
          quote?: string | null
          state?: Database["public"]["Enums"]["commitment_state"]
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
        ]
      }
      escalations: {
        Row: {
          brief: string
          call_id: string
          computation: Json
          created_at: string
          id: string
          state: Database["public"]["Enums"]["escalation_state"]
        }
        Insert: {
          brief: string
          call_id: string
          computation?: Json
          created_at?: string
          id?: string
          state?: Database["public"]["Enums"]["escalation_state"]
        }
        Update: {
          brief?: string
          call_id?: string
          computation?: Json
          created_at?: string
          id?: string
          state?: Database["public"]["Enums"]["escalation_state"]
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
          created_at: string
          currency: string
          id: string
          max_amount: number
          operation_id: string
          pickup_window_end: string | null
          pickup_window_start: string | null
          target_amount: number
        }
        Insert: {
          created_at?: string
          currency?: string
          id?: string
          max_amount: number
          operation_id: string
          pickup_window_end?: string | null
          pickup_window_start?: string | null
          target_amount: number
        }
        Update: {
          created_at?: string
          currency?: string
          id?: string
          max_amount?: number
          operation_id?: string
          pickup_window_end?: string | null
          pickup_window_start?: string | null
          target_amount?: number
        }
        Relationships: [
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
          container: string
          created_at: string
          demurrage_per_day: number
          destination: string
          free_time_ends: string
          id: string
          origin: string
          ref: string
        }
        Insert: {
          container: string
          created_at?: string
          demurrage_per_day?: number
          destination: string
          free_time_ends: string
          id?: string
          origin: string
          ref: string
        }
        Update: {
          container?: string
          created_at?: string
          demurrage_per_day?: number
          destination?: string
          free_time_ends?: string
          id?: string
          origin?: string
          ref?: string
        }
        Relationships: []
      }
      policy_events: {
        Row: {
          ask: string
          call_id: string
          created_at: string
          decision: Database["public"]["Enums"]["policy_decision"]
          id: string
          reason: string | null
        }
        Insert: {
          ask: string
          call_id: string
          created_at?: string
          decision: Database["public"]["Enums"]["policy_decision"]
          id?: string
          reason?: string | null
        }
        Update: {
          ask?: string
          call_id?: string
          created_at?: string
          decision?: Database["public"]["Enums"]["policy_decision"]
          id?: string
          reason?: string | null
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
      utterances: {
        Row: {
          call_id: string
          created_at: string
          id: string
          interrupted: boolean
          speaker: string
          t_end_ms: number | null
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
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
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
      commitment_state: "proposed" | "anchored" | "void"
      escalation_state: "open" | "approved" | "rejected"
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
      commitment_state: ["proposed", "anchored", "void"],
      escalation_state: ["open", "approved", "rejected"],
      policy_decision: ["allow", "deny", "block", "escalate"],
    },
  },
} as const
