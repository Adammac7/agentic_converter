// =============================================================================
// File:        canfd_controller.sv
// Description: CAN FD (Flexible Data-rate) Controller
//              Modeled after the FlexCAN / MCAN peripheral family found in
//              NXP S32K, LPC55, and i.MX RT series devices.
//
//              Hierarchy
//              ---------
//              canfd_pkg                    (package: types, structs, params)
//              canfd_controller  [TOP]
//                ├── canfd_regmap          (APB slave, register bank)
//                ├── canfd_btu             (Bit Timing Unit — baud rate gen)
//                ├── canfd_txrx            (Bit-level TX/RX serialiser)
//                ├── canfd_stuffing        (Bit-stuffing / de-stuffing)
//                ├── canfd_crc             (CRC-15 / CRC-17 / CRC-21)
//                ├── canfd_frame_rx        (Frame assembler — RX path)
//                ├── canfd_frame_tx        (Frame builder  — TX path)
//                ├── canfd_msg_ram         (Message RAM: 64 MB objects)
//                └── canfd_error_handler   (Error counters, fault confinement)
//
// Protocol:    ISO 11898-1:2015 (CAN FD)
// Target:      NXP S32K3xx / i.MX RT117x class devices
// Author:      Embedded Platform Group
// Rev:         2.3.1
// =============================================================================

`timescale 1ns / 1ps
`default_nettype none

// =============================================================================
// PACKAGE
// =============================================================================
package canfd_pkg;

  // ---------------------------------------------------------------------------
  // Bus states
  // ---------------------------------------------------------------------------
  typedef enum logic [1:0] {
    BUS_IDLE        = 2'b00,
    BUS_ACTIVE_RX   = 2'b01,
    BUS_ACTIVE_TX   = 2'b10,
    BUS_OFF         = 2'b11
  } bus_state_e;

  // ---------------------------------------------------------------------------
  // Frame types
  // ---------------------------------------------------------------------------
  typedef enum logic [2:0] {
    FRAME_DATA      = 3'b000,
    FRAME_REMOTE    = 3'b001,
    FRAME_ERROR     = 3'b010,
    FRAME_OVERLOAD  = 3'b011,
    FRAME_INTERFRAME= 3'b100
  } frame_type_e;

  // ---------------------------------------------------------------------------
  // Error types (ISO 11898 fault confinement)
  // ---------------------------------------------------------------------------
  typedef enum logic [2:0] {
    ERR_NONE        = 3'b000,
    ERR_BIT         = 3'b001,
    ERR_STUFF       = 3'b010,
    ERR_CRC         = 3'b011,
    ERR_FORM        = 3'b100,
    ERR_ACK         = 3'b101
  } error_type_e;

  // ---------------------------------------------------------------------------
  // Node state (fault confinement)
  // ---------------------------------------------------------------------------
  typedef enum logic [1:0] {
    NODE_ERROR_ACTIVE  = 2'b00,
    NODE_ERROR_PASSIVE = 2'b01,
    NODE_BUS_OFF       = 2'b10
  } node_state_e;

  // ---------------------------------------------------------------------------
  // CAN FD frame descriptor (passed between sub-modules)
  // ---------------------------------------------------------------------------
  typedef struct packed {
    logic        fd_frame;       // 1 = CAN FD, 0 = Classic CAN
    logic        brs;            // Bit Rate Switch
    logic        esi;            // Error State Indicator
    logic        ide;            // Extended ID
    logic        rtr;            // Remote Transmission Request
    logic [28:0] id;             // 29-bit ID (11-bit standard in [28:18])
    logic [3:0]  dlc;            // Data Length Code
    logic [7:0]  data [0:63];   // Up to 64 bytes (CAN FD)
    logic [20:0] crc_field;      // CRC (15/17/21 bits, MSB-aligned)
  } canfd_frame_t;

  // ---------------------------------------------------------------------------
  // Message buffer entry (stored in message RAM)
  // ---------------------------------------------------------------------------
  typedef struct packed {
    logic        valid;
    logic        pending_tx;
    logic        tx_done;
    logic        rx_done;
    logic [3:0]  priority;       // TX priority (0 = highest)
    canfd_frame_t frame;
  } msg_buf_t;

  // ---------------------------------------------------------------------------
  // Bit timing configuration
  // ---------------------------------------------------------------------------
  typedef struct packed {
    logic [7:0]  brp;            // Baud Rate Prescaler
    logic [6:0]  tseg1;          // Time Segment 1 (prop + phase1)
    logic [4:0]  tseg2;          // Time Segment 2 (phase2)
    logic [4:0]  sjw;            // Synchronisation Jump Width
  } bit_timing_t;

  // ---------------------------------------------------------------------------
  // DLC → byte count LUT (CAN FD)
  // ---------------------------------------------------------------------------
  function automatic logic [6:0] dlc_to_bytes(input logic [3:0] dlc);
    case (dlc)
      4'd0:    dlc_to_bytes = 7'd0;
      4'd1:    dlc_to_bytes = 7'd1;
      4'd2:    dlc_to_bytes = 7'd2;
      4'd3:    dlc_to_bytes = 7'd3;
      4'd4:    dlc_to_bytes = 7'd4;
      4'd5:    dlc_to_bytes = 7'd5;
      4'd6:    dlc_to_bytes = 7'd6;
      4'd7:    dlc_to_bytes = 7'd7;
      4'd8:    dlc_to_bytes = 7'd8;
      4'd9:    dlc_to_bytes = 7'd12;
      4'd10:   dlc_to_bytes = 7'd16;
      4'd11:   dlc_to_bytes = 7'd20;
      4'd12:   dlc_to_bytes = 7'd24;
      4'd13:   dlc_to_bytes = 7'd32;
      4'd14:   dlc_to_bytes = 7'd48;
      default: dlc_to_bytes = 7'd64;
    endcase
  endfunction

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  localparam int unsigned MSG_BUF_COUNT  = 64;   // Message buffers
  localparam int unsigned APB_ADDR_W     = 12;
  localparam int unsigned APB_DATA_W     = 32;

endpackage : canfd_pkg

// =============================================================================
// SUB-MODULE 1: canfd_regmap
// APB slave register bank.  All controller configuration lives here.
// =============================================================================
import canfd_pkg::*;

module canfd_regmap #(
  parameter int unsigned ADDR_W = canfd_pkg::APB_ADDR_W,
  parameter int unsigned DATA_W = canfd_pkg::APB_DATA_W
)(
  input  logic              pclk,
  input  logic              presetn,

  // APB slave
  input  logic [ADDR_W-1:0] paddr,
  input  logic              psel,
  input  logic              penable,
  input  logic              pwrite,
  input  logic [DATA_W-1:0] pwdata,
  output logic [DATA_W-1:0] prdata,
  output logic              pready,
  output logic              pslverr,

  // Register outputs (to rest of controller)
  output bit_timing_t       reg_nom_timing,    // Nominal bit timing
  output bit_timing_t       reg_fd_timing,     // FD data-phase bit timing
  output logic              reg_fd_enable,     // CAN FD mode enable
  output logic              reg_tx_enable,     // TX enable
  output logic              reg_loopback,      // Internal loopback
  output logic              reg_listenonly,    // Listen-only mode
  output logic [5:0]        reg_tx_buf_sel,    // TX buffer index to transmit
  output logic              reg_tx_request,    // One-shot TX request (pulse)
  output logic [7:0]        reg_rx_filter_id,  // Acceptance filter (basic)
  output logic [7:0]        reg_rx_filter_mask,

  // Status inputs (from rest of controller → readable by CPU)
  input  logic              sta_bus_off,
  input  logic              sta_error_passive,
  input  logic [7:0]        sta_tec,           // TX error counter
  input  logic [7:0]        sta_rec,           // RX error counter
  input  logic              sta_rx_ready,      // RX frame available
  input  logic [5:0]        sta_rx_buf_idx,    // Which buffer has new RX data
  input  logic              sta_tx_done,
  input  error_type_e       sta_last_error,

  // Interrupt output
  output logic              irq_out
);

  // --------------------------------------------------------------------------
  // Register addresses (word-aligned, 4-byte stride)
  // --------------------------------------------------------------------------
  localparam logic [ADDR_W-1:0]
    ADDR_MCR       = 12'h000,   // Module Control Register
    ADDR_CTRL1     = 12'h004,   // Control 1 (nominal timing)
    ADDR_CTRL2     = 12'h008,   // Control 2 (FD timing)
    ADDR_STATUS    = 12'h00C,   // Status (RO)
    ADDR_ECR       = 12'h010,   // Error Counter Register (RO)
    ADDR_ESR       = 12'h014,   // Error Status Register
    ADDR_IMASK     = 12'h018,   // Interrupt Mask
    ADDR_IFLAG     = 12'h01C,   // Interrupt Flag (W1C)
    ADDR_RXFILT_ID = 12'h020,   // RX acceptance filter ID
    ADDR_RXFILT_MK = 12'h024,   // RX acceptance filter mask
    ADDR_TXREQ     = 12'h028;   // TX request (buf index + go bit)

  // --------------------------------------------------------------------------
  // Register storage
  // --------------------------------------------------------------------------
  logic [DATA_W-1:0] reg_mcr;
  logic [DATA_W-1:0] reg_ctrl1;
  logic [DATA_W-1:0] reg_ctrl2;
  logic [DATA_W-1:0] reg_imask;
  logic [DATA_W-1:0] reg_iflag;
  logic [DATA_W-1:0] reg_rxfilt_id;
  logic [DATA_W-1:0] reg_rxfilt_mask;
  logic [DATA_W-1:0] reg_txreq;

  logic              tx_request_pulse;

  // --------------------------------------------------------------------------
  // APB write
  // --------------------------------------------------------------------------
  always_ff @(posedge pclk or negedge presetn) begin
    if (!presetn) begin
      reg_mcr        <= 32'h0000_5980; // FD disabled, error-active defaults
      reg_ctrl1      <= 32'h00DB_0006; // 500 kbit/s nominal @ 80 MHz
      reg_ctrl2      <= 32'h00430003; // 2 Mbit/s data phase
      reg_imask      <= 32'h0000_0003; // RX + TX interrupts enabled
      reg_iflag      <= '0;
      reg_rxfilt_id  <= '0;
      reg_rxfilt_mask<= '0;
      reg_txreq      <= '0;
      tx_request_pulse <= 1'b0;
    end else begin
      tx_request_pulse <= 1'b0;

      // Latch new interrupt flags from hardware events
      if (sta_rx_ready)  reg_iflag[0] <= 1'b1;
      if (sta_tx_done)   reg_iflag[1] <= 1'b1;
      if (sta_bus_off)   reg_iflag[2] <= 1'b1;

      if (psel && penable && pwrite) begin
        case (paddr)
          ADDR_MCR:       reg_mcr         <= pwdata;
          ADDR_CTRL1:     reg_ctrl1       <= pwdata;
          ADDR_CTRL2:     reg_ctrl2       <= pwdata;
          ADDR_IMASK:     reg_imask       <= pwdata;
          ADDR_IFLAG:     reg_iflag       <= reg_iflag & ~pwdata; // W1C
          ADDR_RXFILT_ID: reg_rxfilt_id   <= pwdata;
          ADDR_RXFILT_MK: reg_rxfilt_mask <= pwdata;
          ADDR_TXREQ: begin
            reg_txreq        <= pwdata;
            tx_request_pulse <= pwdata[31]; // Bit 31 = TX GO
          end
          default: ; // Ignore unknown
        endcase
      end
    end
  end

  // --------------------------------------------------------------------------
  // APB read
  // --------------------------------------------------------------------------
  always_ff @(posedge pclk or negedge presetn) begin
    if (!presetn) begin
      prdata  <= '0;
      pslverr <= 1'b0;
    end else if (psel && !penable) begin
      pslverr <= 1'b0;
      case (paddr)
        ADDR_MCR:       prdata <= reg_mcr;
        ADDR_CTRL1:     prdata <= reg_ctrl1;
        ADDR_CTRL2:     prdata <= reg_ctrl2;
        ADDR_STATUS:    prdata <= {22'b0,
                                   sta_bus_off,
                                   sta_error_passive,
                                   sta_rx_ready,
                                   sta_tx_done,
                                   sta_rx_buf_idx};
        ADDR_ECR:       prdata <= {sta_tec, sta_rec, 16'b0};
        ADDR_ESR:       prdata <= {29'b0, sta_last_error};
        ADDR_IMASK:     prdata <= reg_imask;
        ADDR_IFLAG:     prdata <= reg_iflag;
        ADDR_RXFILT_ID: prdata <= reg_rxfilt_id;
        ADDR_RXFILT_MK: prdata <= reg_rxfilt_mask;
        default: begin
          prdata  <= 32'hDEAD_BEEF;
          pslverr <= 1'b1;
        end
      endcase
    end
  end

  assign pready = 1'b1; // Zero wait-state APB3

  // --------------------------------------------------------------------------
  // Decode register fields → structured outputs
  // --------------------------------------------------------------------------
  assign reg_nom_timing.brp   = reg_ctrl1[7:0];
  assign reg_nom_timing.tseg1 = reg_ctrl1[14:8];
  assign reg_nom_timing.tseg2 = reg_ctrl1[19:15];
  assign reg_nom_timing.sjw   = reg_ctrl1[24:20];

  assign reg_fd_timing.brp    = reg_ctrl2[7:0];
  assign reg_fd_timing.tseg1  = reg_ctrl2[11:8];
  assign reg_fd_timing.tseg2  = reg_ctrl2[15:12];
  assign reg_fd_timing.sjw    = reg_ctrl2[19:16];

  assign reg_fd_enable   = reg_mcr[11];
  assign reg_tx_enable   = ~reg_mcr[4];   // MDIS bit inverted
  assign reg_loopback    = reg_mcr[15];
  assign reg_listenonly  = reg_mcr[14];
  assign reg_tx_buf_sel  = reg_txreq[5:0];
  assign reg_tx_request  = tx_request_pulse;
  assign reg_rx_filter_id   = reg_rxfilt_id[7:0];
  assign reg_rx_filter_mask = reg_rxfilt_mask[7:0];

  // Interrupt: any unmasked flag
  assign irq_out = |(reg_iflag & reg_imask);

endmodule : canfd_regmap

// =============================================================================
// SUB-MODULE 2: canfd_btu
// Bit Timing Unit — generates the sample-point clock enable and
// synchronisation signals from the system clock.
// =============================================================================
import canfd_pkg::*;

module canfd_btu (
  input  logic        clk,
  input  logic        rst_n,

  input  bit_timing_t nom_timing,
  input  bit_timing_t fd_timing,
  input  logic        fd_active,     // 1 = use FD data-phase timing
  input  logic        hard_sync_req, // From RX — edge-triggered resync

  output logic        tq_pulse,      // Time-quantum tick
  output logic        sample_point,  // Sample this bit
  output logic        tx_point,      // Drive TX output now
  output logic        seg1_active,   // In TSEG1 (for stuffing module)
  output logic [7:0]  tq_count       // Debug: TQ counter within bit
);

  // --------------------------------------------------------------------------
  // Select active timing config
  // --------------------------------------------------------------------------
  bit_timing_t active_timing;
  assign active_timing = fd_active ? fd_timing : nom_timing;

  // --------------------------------------------------------------------------
  // BRP prescaler — divides clk down to Time Quanta
  // --------------------------------------------------------------------------
  logic [7:0]  brp_cnt;
  logic        brp_tick;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      brp_cnt  <= '0;
      brp_tick <= 1'b0;
    end else begin
      brp_tick <= 1'b0;
      if (brp_cnt == active_timing.brp) begin
        brp_cnt  <= '0;
        brp_tick <= 1'b1;
      end else begin
        brp_cnt <= brp_cnt + 1;
      end
    end
  end

  assign tq_pulse = brp_tick;

  // --------------------------------------------------------------------------
  // Bit segment counter (SYNC_SEG + TSEG1 + TSEG2)
  // --------------------------------------------------------------------------
  // Bit structure:
  //   TQ 0          : SYNC_SEG (always 1 TQ)
  //   TQ 1..tseg1   : TSEG1 (propagation + phase1)
  //   TQ tseg1+1..N : TSEG2 (phase2)
  //
  logic [6:0]  bit_tq_cnt;   // TQ counter within current bit
  logic [6:0]  bit_period;   // Total TQs per bit

  assign bit_period = 7'd1 + {2'b0, active_timing.tseg1} + {2'b0, active_timing.tseg2};

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      bit_tq_cnt  <= '0;
      sample_point<= 1'b0;
      tx_point    <= 1'b0;
      seg1_active <= 1'b0;
    end else begin
      sample_point <= 1'b0;
      tx_point     <= 1'b0;

      if (hard_sync_req) begin
        // Hard synchronisation: restart bit at TQ 1
        bit_tq_cnt  <= 7'd1;
        seg1_active <= 1'b1;
      end else if (brp_tick) begin
        if (bit_tq_cnt >= bit_period - 1) begin
          bit_tq_cnt  <= '0;
          tx_point    <= 1'b1;   // Start of new bit — drive TX
          seg1_active <= 1'b1;
        end else begin
          bit_tq_cnt <= bit_tq_cnt + 1;

          // Sample point at end of TSEG1
          if (bit_tq_cnt == {2'b0, active_timing.tseg1}) begin
            sample_point <= 1'b1;
            seg1_active  <= 1'b0;
          end
        end
      end
    end
  end

  assign tq_count = {1'b0, bit_tq_cnt};

endmodule : canfd_btu

// =============================================================================
// SUB-MODULE 3: canfd_crc
// Computes CRC-15 (classic CAN), CRC-17, or CRC-21 (CAN FD)
// depending on frame type and payload length.
// =============================================================================
import canfd_pkg::*;

module canfd_crc (
  input  logic        clk,
  input  logic        rst_n,

  input  logic        enable,        // Process bits while high
  input  logic        data_bit,      // Serial input bit
  input  logic        fd_frame,      // 1 = CAN FD (use 17 or 21 bit CRC)
  input  logic        long_payload,  // Payload > 16 bytes → CRC-21
  input  logic        crc_reset,     // Synchronous reset of shift register

  output logic [20:0] crc_out,       // Always 21 bits wide; trim as needed
  output logic        crc_valid      // Pulses when CRC is complete
);

  // CAN polynomials
  localparam logic [14:0] POLY_15 = 15'h4599;
  localparam logic [16:0] POLY_17 = 17'h1685B;
  localparam logic [20:0] POLY_21 = 21'h102899;

  logic [14:0] crc15;
  logic [16:0] crc17;
  logic [20:0] crc21;
  logic        crc15_fb, crc17_fb, crc21_fb;

  // CRC-15 (classic CAN)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || crc_reset)
      crc15 <= '0;
    else if (enable) begin
      crc15_fb = data_bit ^ crc15[14];
      crc15    <= {crc15[13:0], 1'b0} ^ (crc15_fb ? POLY_15 : 15'b0);
    end
  end

  // CRC-17 (CAN FD, ≤16 bytes payload)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || crc_reset)
      crc17 <= '0;
    else if (enable) begin
      crc17_fb = data_bit ^ crc17[16];
      crc17    <= {crc17[15:0], 1'b0} ^ (crc17_fb ? POLY_17 : 17'b0);
    end
  end

  // CRC-21 (CAN FD, >16 bytes payload)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || crc_reset)
      crc21 <= '0;
    else if (enable) begin
      crc21_fb = data_bit ^ crc21[20];
      crc21    <= {crc21[19:0], 1'b0} ^ (crc21_fb ? POLY_21 : 21'b0);
    end
  end

  // Output mux
  always_comb begin
    if (!fd_frame)
      crc_out = {6'b0, crc15};
    else if (!long_payload)
      crc_out = {4'b0, crc17};
    else
      crc_out = crc21;
  end

  assign crc_valid = 1'b0; // Driven by frame_rx/tx based on bit count

endmodule : canfd_crc

// =============================================================================
// SUB-MODULE 4: canfd_stuffing
// Bit stuffing (TX) and de-stuffing (RX) per ISO 11898-1.
// After 5 consecutive identical bits, insert/expect a complement bit.
// CAN FD uses a fixed-stuff scheme in the CRC field.
// =============================================================================
import canfd_pkg::*;

module canfd_stuffing (
  input  logic  clk,
  input  logic  rst_n,

  // Mode
  input  logic  tx_mode,       // 1 = TX stuffing, 0 = RX de-stuffing
  input  logic  fd_frame,
  input  logic  in_crc_field,  // Stuff counting changes in FD CRC field

  // Data flow
  input  logic  bit_in,        // Raw bit from TX serialiser or RX line
  input  logic  bit_en,        // Process this TQ
  output logic  bit_out,       // Stuffed (TX) or de-stuffed (RX) bit
  output logic  bit_out_valid, // Qualified output

  // Error
  output logic  stuff_error    // RX: got 6+ identical bits (classic CAN)
);

  logic [2:0] run_len;   // Consecutive identical bit count
  logic       last_bit;
  logic       insert_pending;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      run_len        <= 3'd1;
      last_bit       <= 1'b1;   // Bus idles recessive
      insert_pending <= 1'b0;
      stuff_error    <= 1'b0;
      bit_out        <= 1'b1;
      bit_out_valid  <= 1'b0;
    end else begin
      bit_out_valid <= 1'b0;
      stuff_error   <= 1'b0;

      if (bit_en) begin
        if (tx_mode) begin
          // ── TX: insert stuff bit after 5 identical bits ──────────────────
          if (insert_pending) begin
            bit_out        <= ~last_bit;  // Complement stuff bit
            bit_out_valid  <= 1'b1;
            insert_pending <= 1'b0;
            run_len        <= 3'd1;
            last_bit       <= ~last_bit;
          end else begin
            bit_out       <= bit_in;
            bit_out_valid <= 1'b1;
            if (bit_in == last_bit) begin
              if (run_len == 3'd4)
                insert_pending <= 1'b1;
              else
                run_len <= run_len + 1;
            end else begin
              run_len  <= 3'd1;
              last_bit <= bit_in;
            end
          end
        end else begin
          // ── RX: detect and remove stuff bits ─────────────────────────────
          if (bit_in == last_bit) begin
            if (run_len == 3'd4) begin
              // Next bit must be complement (stuff bit) — discard it
              run_len       <= 3'd1;
              bit_out_valid <= 1'b0; // Consumed as stuff
            end else if (run_len >= 3'd5) begin
              stuff_error   <= 1'b1;
              bit_out_valid <= 1'b0;
            end else begin
              run_len       <= run_len + 1;
              bit_out       <= bit_in;
              bit_out_valid <= 1'b1;
            end
          end else begin
            run_len       <= 3'd1;
            last_bit      <= bit_in;
            bit_out       <= bit_in;
            bit_out_valid <= 1'b1;
          end
        end
      end
    end
  end

endmodule : canfd_stuffing

// =============================================================================
// SUB-MODULE 5: canfd_txrx
// Physical-layer serialiser / deserialiser.
// Drives CAN_TX and samples CAN_RX at the sample point.
// Also performs bit monitoring (TX ≠ RX → bit error).
// =============================================================================
import canfd_pkg::*;

module canfd_txrx (
  input  logic  clk,
  input  logic  rst_n,

  // Timing
  input  logic  sample_point,
  input  logic  tx_point,

  // Control
  input  logic  tx_enable,
  input  logic  loopback,

  // Data from frame builder
  input  logic  tx_bit,       // Serial bit to transmit
  input  logic  tx_bit_valid, // TX serialiser has valid data

  // Physical pins
  output logic  can_tx,
  input  logic  can_rx,

  // Outputs to frame assembler
  output logic  rx_bit,
  output logic  rx_bit_valid,

  // Error
  output logic  bit_error,     // Transmitted dominant, received recessive (or vice versa)

  // Bus state
  output bus_state_e bus_state
);

  logic can_rx_sync;    // Synchronised RX input
  logic tx_bit_r;       // Registered TX bit

  // Double-flop synchroniser on RX input
  logic rx_ff1, rx_ff2;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      {rx_ff2, rx_ff1} <= 2'b11; // Recessive idle
    else
      {rx_ff2, rx_ff1} <= {rx_ff1, can_rx};
  end
  assign can_rx_sync = loopback ? can_tx : rx_ff2;

  // Register TX bit at tx_point
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      tx_bit_r <= 1'b1; // Recessive
    else if (tx_point)
      tx_bit_r <= tx_bit_valid ? tx_bit : 1'b1;
  end

  assign can_tx = tx_enable ? tx_bit_r : 1'b1;

  // Sample RX at sample point
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rx_bit       <= 1'b1;
      rx_bit_valid <= 1'b0;
      bit_error    <= 1'b0;
    end else begin
      rx_bit_valid <= 1'b0;
      bit_error    <= 1'b0;
      if (sample_point) begin
        rx_bit       <= can_rx_sync;
        rx_bit_valid <= 1'b1;
        // Bit monitoring: only check during TX
        if (tx_bit_valid && tx_enable)
          bit_error <= (tx_bit_r != can_rx_sync);
      end
    end
  end

  // Bus state detection
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      bus_state <= BUS_IDLE;
    else begin
      if (!tx_enable)
        bus_state <= BUS_IDLE;
      else if (tx_bit_valid)
        bus_state <= BUS_ACTIVE_TX;
      else
        bus_state <= BUS_ACTIVE_RX;
    end
  end

endmodule : canfd_txrx

// =============================================================================
// SUB-MODULE 6: canfd_frame_rx
// Frame assembler — RX path.
// Collects de-stuffed bits from the line, assembles the full CAN / CAN FD
// frame field by field, validates CRC, checks acceptance filter,
// and writes the result to the message RAM.
// =============================================================================
import canfd_pkg::*;

module canfd_frame_rx (
  input  logic        clk,
  input  logic        rst_n,

  // De-stuffed bit stream
  input  logic        rx_bit,
  input  logic        rx_bit_valid,

  // CRC result (from canfd_crc)
  input  logic [20:0] crc_computed,
  output logic        crc_reset,
  output logic        crc_enable,

  // Error inputs
  input  logic        stuff_error,
  input  logic        bit_error,

  // Acceptance filter
  input  logic [7:0]  filter_id,
  input  logic [7:0]  filter_mask,

  // Frame output → message RAM
  output canfd_frame_t rx_frame,
  output logic         rx_frame_valid,  // Pulse: write to RAM
  output logic [5:0]   rx_buf_idx,      // Which buffer to write

  // Error reporting
  output error_type_e  rx_error,
  output logic         rx_error_valid,

  // ACK slot control
  output logic         send_ack
);

  // --------------------------------------------------------------------------
  // RX FSM state encoding
  // --------------------------------------------------------------------------
  typedef enum logic [4:0] {
    RX_IDLE,
    RX_SOF,
    RX_ID_A,        // Base ID [10:0]
    RX_SRR_RTR,     // SRR (extended) or RTR (base)
    RX_IDE,
    RX_ID_B,        // Extended ID [17:0]
    RX_RTR_EXT,
    RX_RES_FDF,     // Reserved / FD frame bit
    RX_BRS,
    RX_ESI,
    RX_DLC,
    RX_DATA,
    RX_CRC_SEQ,
    RX_CRC_DEL,
    RX_ACK_SLOT,
    RX_ACK_DEL,
    RX_EOF,
    RX_IFS,
    RX_ERROR_FLAG
  } rx_state_e;

  rx_state_e   rx_state;
  canfd_frame_t frame_build;
  logic [5:0]  bit_pos;       // Bit position within current field
  logic [6:0]  data_byte_idx;
  logic [6:0]  data_bit_idx;
  logic [6:0]  bytes_expected;
  logic [20:0] rx_crc_field;
  logic        filter_pass;

  // Acceptance filter (basic mask filter on 8 MSBs of ID)
  assign filter_pass = ((frame_build.id[28:21] & filter_mask) ==
                        (filter_id              & filter_mask));

  // Static RX buffer allocation (round-robin; simplified)
  logic [5:0] rx_buf_ptr;
  assign rx_buf_idx = rx_buf_ptr;

  assign crc_enable = rx_bit_valid &&
                      (rx_state != RX_IDLE) &&
                      (rx_state != RX_CRC_SEQ) &&
                      (rx_state != RX_CRC_DEL) &&
                      (rx_state != RX_ACK_SLOT) &&
                      (rx_state != RX_ACK_DEL) &&
                      (rx_state != RX_EOF) &&
                      (rx_state != RX_IFS);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rx_state       <= RX_IDLE;
      rx_frame_valid <= 1'b0;
      rx_error_valid <= 1'b0;
      rx_error       <= ERR_NONE;
      send_ack       <= 1'b0;
      crc_reset      <= 1'b1;
      bit_pos        <= '0;
      data_byte_idx  <= '0;
      data_bit_idx   <= '0;
      rx_crc_field   <= '0;
      rx_buf_ptr     <= '0;
      frame_build    <= '0;
    end else begin
      rx_frame_valid <= 1'b0;
      rx_error_valid <= 1'b0;
      send_ack       <= 1'b0;
      crc_reset      <= 1'b0;

      // Error injection from other sub-modules
      if (stuff_error && rx_state != RX_IDLE) begin
        rx_error       <= ERR_STUFF;
        rx_error_valid <= 1'b1;
        rx_state       <= RX_ERROR_FLAG;
        crc_reset      <= 1'b1;
      end else if (rx_bit_valid) begin

        case (rx_state)

          RX_IDLE: begin
            if (!rx_bit) begin // Dominant = SOF
              crc_reset   <= 1'b1;
              frame_build <= '0;
              rx_state    <= RX_SOF;
            end
          end

          RX_SOF: rx_state <= RX_ID_A;

          RX_ID_A: begin
            frame_build.id[28 - bit_pos] <= rx_bit;
            if (bit_pos == 6'd10) begin
              bit_pos  <= '0;
              rx_state <= RX_SRR_RTR;
            end else
              bit_pos <= bit_pos + 1;
          end

          RX_SRR_RTR: begin
            frame_build.rtr <= rx_bit;
            rx_state        <= RX_IDE;
          end

          RX_IDE: begin
            frame_build.ide <= rx_bit;
            rx_state        <= rx_bit ? RX_ID_B : RX_RES_FDF;
          end

          RX_ID_B: begin
            frame_build.id[17 - bit_pos] <= rx_bit;
            if (bit_pos == 6'd17) begin
              bit_pos  <= '0;
              rx_state <= RX_RTR_EXT;
            end else
              bit_pos <= bit_pos + 1;
          end

          RX_RTR_EXT: begin
            frame_build.rtr <= rx_bit;
            rx_state        <= RX_RES_FDF;
          end

          RX_RES_FDF: begin
            frame_build.fd_frame <= rx_bit; // FDF bit
            rx_state <= frame_build.fd_frame ? RX_BRS : RX_DLC;
          end

          RX_BRS: begin
            frame_build.brs <= rx_bit;
            rx_state        <= RX_ESI;
          end

          RX_ESI: begin
            frame_build.esi <= rx_bit;
            rx_state        <= RX_DLC;
          end

          RX_DLC: begin
            frame_build.dlc[3 - bit_pos[1:0]] <= rx_bit;
            if (bit_pos[1:0] == 2'd3) begin
              bit_pos       <= '0;
              data_byte_idx <= '0;
              data_bit_idx  <= '0;
              bytes_expected<= dlc_to_bytes(frame_build.dlc);
              rx_state      <= (bytes_expected == 0) ? RX_CRC_SEQ : RX_DATA;
            end else
              bit_pos <= bit_pos + 1;
          end

          RX_DATA: begin
            frame_build.data[data_byte_idx][7 - data_bit_idx[2:0]] <= rx_bit;
            if (data_bit_idx[2:0] == 3'd7) begin
              data_bit_idx  <= '0;
              data_byte_idx <= data_byte_idx + 1;
              if (data_byte_idx + 1 >= bytes_expected) begin
                bit_pos  <= '0;
                rx_state <= RX_CRC_SEQ;
              end
            end else
              data_bit_idx <= data_bit_idx + 1;
          end

          RX_CRC_SEQ: begin
            // Collect received CRC field (21 bits max)
            rx_crc_field[20 - bit_pos] <= rx_bit;
            if (bit_pos == 6'd20 ||
                (!frame_build.fd_frame && bit_pos == 6'd14)) begin
              bit_pos  <= '0;
              rx_state <= RX_CRC_DEL;
            end else
              bit_pos <= bit_pos + 1;
          end

          RX_CRC_DEL: begin
            // Validate CRC delimiter (must be recessive)
            if (!rx_bit) begin
              rx_error       <= ERR_FORM;
              rx_error_valid <= 1'b1;
              rx_state       <= RX_ERROR_FLAG;
            end else begin
              // Compare computed vs received CRC
              if (rx_crc_field != crc_computed) begin
                rx_error       <= ERR_CRC;
                rx_error_valid <= 1'b1;
                rx_state       <= RX_ERROR_FLAG;
              end else begin
                send_ack <= 1'b1;
                rx_state <= RX_ACK_SLOT;
              end
            end
          end

          RX_ACK_SLOT:  rx_state <= RX_ACK_DEL;
          RX_ACK_DEL:   rx_state <= RX_EOF;

          RX_EOF: begin
            bit_pos <= bit_pos + 1;
            if (bit_pos == 6'd6) begin
              bit_pos  <= '0;
              rx_state <= RX_IFS;
              // Accept frame if filter passes
              if (filter_pass) begin
                rx_frame       <= frame_build;
                rx_frame_valid <= 1'b1;
                rx_buf_ptr     <= rx_buf_ptr + 1;
              end
            end
          end

          RX_IFS: begin
            bit_pos <= bit_pos + 1;
            if (bit_pos == 6'd2) begin
              bit_pos  <= '0;
              rx_state <= RX_IDLE;
            end
          end

          RX_ERROR_FLAG: begin
            // Transmit 6-bit error flag then return to idle
            bit_pos <= bit_pos + 1;
            if (bit_pos == 6'd5) begin
              bit_pos   <= '0;
              rx_state  <= RX_IDLE;
              crc_reset <= 1'b1;
            end
          end

          default: rx_state <= RX_IDLE;

        endcase
      end
    end
  end

endmodule : canfd_frame_rx

// =============================================================================
// SUB-MODULE 7: canfd_frame_tx
// Frame builder — TX path.
// Reads a frame descriptor from the message RAM and serialises it
// bit-by-bit into the stuffing module.
// =============================================================================
import canfd_pkg::*;

module canfd_frame_tx (
  input  logic        clk,
  input  logic        rst_n,

  // TX timing
  input  logic        tx_point,

  // Frame to send (from message RAM)
  input  canfd_frame_t tx_frame,
  input  logic         tx_frame_valid,   // Pulse: new frame to transmit
  output logic         tx_frame_ack,     // Pulse: frame accepted, begin TX

  // ACK received from bus (from frame_rx)
  input  logic         ack_received,

  // Serial output → stuffing module
  output logic         tx_bit,
  output logic         tx_bit_valid,

  // Status
  output logic         tx_done,          // Pulse on successful transmission
  output logic         tx_active,
  output error_type_e  tx_error,
  output logic         tx_error_valid
);

  typedef enum logic [3:0] {
    TX_IDLE,
    TX_SOF,
    TX_ID_A,
    TX_SRR_IDE,
    TX_ID_B,
    TX_RTR_FDF,
    TX_BRS,
    TX_ESI,
    TX_DLC,
    TX_DATA,
    TX_CRC,
    TX_CRC_DEL,
    TX_ACK,
    TX_EOF,
    TX_IFS
  } tx_state_e;

  tx_state_e    tx_state;
  canfd_frame_t tx_buf;
  logic [5:0]   bit_pos;
  logic [6:0]   data_byte_idx;
  logic [2:0]   data_bit_idx;
  logic [6:0]   bytes_to_send;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      tx_state      <= TX_IDLE;
      tx_bit        <= 1'b1;
      tx_bit_valid  <= 1'b0;
      tx_done       <= 1'b0;
      tx_active     <= 1'b0;
      tx_frame_ack  <= 1'b0;
      tx_error_valid<= 1'b0;
      tx_error      <= ERR_NONE;
      bit_pos       <= '0;
      data_byte_idx <= '0;
      data_bit_idx  <= '0;
    end else begin
      tx_done        <= 1'b0;
      tx_frame_ack   <= 1'b0;
      tx_error_valid <= 1'b0;

      if (tx_point) begin
        tx_bit_valid <= 1'b0;

        case (tx_state)

          TX_IDLE: begin
            tx_active <= 1'b0;
            if (tx_frame_valid) begin
              tx_buf        <= tx_frame;
              tx_frame_ack  <= 1'b1;
              tx_active     <= 1'b1;
              bytes_to_send <= dlc_to_bytes(tx_frame.dlc);
              tx_state      <= TX_SOF;
            end
          end

          TX_SOF: begin
            tx_bit       <= 1'b0; // Dominant SOF
            tx_bit_valid <= 1'b1;
            bit_pos      <= '0;
            tx_state     <= TX_ID_A;
          end

          TX_ID_A: begin
            tx_bit       <= tx_buf.id[28 - bit_pos];
            tx_bit_valid <= 1'b1;
            if (bit_pos == 6'd10) begin
              bit_pos  <= '0;
              tx_state <= TX_SRR_IDE;
            end else
              bit_pos <= bit_pos + 1;
          end

          TX_SRR_IDE: begin
            // SRR (extended) = recessive; RTR (base) = frame.rtr
            tx_bit       <= tx_buf.ide ? 1'b1 : tx_buf.rtr;
            tx_bit_valid <= 1'b1;
            tx_state     <= TX_RTR_FDF;
          end

          TX_RTR_FDF: begin
            tx_bit       <= tx_buf.fd_frame;
            tx_bit_valid <= 1'b1;
            tx_state     <= tx_buf.fd_frame ? TX_BRS : TX_DLC;
          end

          TX_BRS: begin
            tx_bit       <= tx_buf.brs;
            tx_bit_valid <= 1'b1;
            tx_state     <= TX_ESI;
          end

          TX_ESI: begin
            tx_bit       <= tx_buf.esi;
            tx_bit_valid <= 1'b1;
            bit_pos      <= '0;
            tx_state     <= TX_DLC;
          end

          TX_DLC: begin
            tx_bit       <= tx_buf.dlc[3 - bit_pos[1:0]];
            tx_bit_valid <= 1'b1;
            if (bit_pos[1:0] == 2'd3) begin
              bit_pos       <= '0;
              data_byte_idx <= '0;
              data_bit_idx  <= '0;
              tx_state      <= (bytes_to_send == 0) ? TX_CRC : TX_DATA;
            end else
              bit_pos <= bit_pos + 1;
          end

          TX_DATA: begin
            tx_bit       <= tx_buf.data[data_byte_idx][7 - data_bit_idx];
            tx_bit_valid <= 1'b1;
            if (data_bit_idx == 3'd7) begin
              data_bit_idx  <= '0;
              data_byte_idx <= data_byte_idx + 1;
              if (data_byte_idx + 1 >= bytes_to_send) begin
                bit_pos  <= '0;
                tx_state <= TX_CRC;
              end
            end else
              data_bit_idx <= data_bit_idx + 1;
          end

          TX_CRC: begin
            tx_bit       <= tx_buf.crc_field[20 - bit_pos];
            tx_bit_valid <= 1'b1;
            if (bit_pos == 6'd20 ||
                (!tx_buf.fd_frame && bit_pos == 6'd14)) begin
              bit_pos  <= '0;
              tx_state <= TX_CRC_DEL;
            end else
              bit_pos <= bit_pos + 1;
          end

          TX_CRC_DEL: begin
            tx_bit       <= 1'b1; // Recessive delimiter
            tx_bit_valid <= 1'b1;
            tx_state     <= TX_ACK;
          end

          TX_ACK: begin
            tx_bit       <= 1'b1; // Release bus for ACK
            tx_bit_valid <= 1'b1;
            tx_state     <= TX_EOF;
            if (!ack_received) begin
              tx_error       <= ERR_ACK;
              tx_error_valid <= 1'b1;
            end
          end

          TX_EOF: begin
            tx_bit       <= 1'b1; // 7 recessive EOF bits
            tx_bit_valid <= 1'b1;
            bit_pos      <= bit_pos + 1;
            if (bit_pos == 6'd6) begin
              bit_pos  <= '0;
              tx_state <= TX_IFS;
            end
          end

          TX_IFS: begin
            tx_bit       <= 1'b1;
            tx_bit_valid <= 1'b1;
            bit_pos      <= bit_pos + 1;
            if (bit_pos == 6'd2) begin
              bit_pos  <= '0;
              tx_done  <= 1'b1;
              tx_state <= TX_IDLE;
            end
          end

          default: tx_state <= TX_IDLE;

        endcase
      end
    end
  end

endmodule : canfd_frame_tx

// =============================================================================
// SUB-MODULE 8: canfd_msg_ram
// Message RAM — 64 message buffer slots.
// Dual-port: CPU writes via APB (through regmap), controller reads/writes.
// =============================================================================
import canfd_pkg::*;

module canfd_msg_ram #(
  parameter int unsigned DEPTH = canfd_pkg::MSG_BUF_COUNT
)(
  input  logic        clk,
  input  logic        rst_n,

  // Controller write port (RX path writes completed frames)
  input  logic        ctrl_wr_en,
  input  logic [5:0]  ctrl_wr_idx,
  input  canfd_frame_t ctrl_wr_data,

  // Controller read port (TX path reads pending frames)
  input  logic [5:0]  ctrl_rd_idx,
  output msg_buf_t    ctrl_rd_data,

  // TX done feedback — mark buffer as transmitted
  input  logic        tx_done_pulse,
  input  logic [5:0]  tx_done_idx,

  // Status outputs
  output logic        any_tx_pending,
  output logic [5:0]  next_tx_idx,    // Highest-priority pending TX buffer
  output logic        any_rx_ready,
  output logic [5:0]  next_rx_idx     // Most recently written RX buffer
);

  msg_buf_t mem [0:DEPTH-1];

  // --------------------------------------------------------------------------
  // Write port
  // --------------------------------------------------------------------------
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < DEPTH; i++)
        mem[i] <= '0;
    end else begin
      if (ctrl_wr_en) begin
        mem[ctrl_wr_idx].valid    <= 1'b1;
        mem[ctrl_wr_idx].rx_done  <= 1'b1;
        mem[ctrl_wr_idx].tx_done  <= 1'b0;
        mem[ctrl_wr_idx].frame    <= ctrl_wr_data;
      end
      if (tx_done_pulse) begin
        mem[tx_done_idx].tx_done     <= 1'b1;
        mem[tx_done_idx].pending_tx  <= 1'b0;
      end
    end
  end

  // --------------------------------------------------------------------------
  // Read port (combinational)
  // --------------------------------------------------------------------------
  assign ctrl_rd_data = mem[ctrl_rd_idx];

  // --------------------------------------------------------------------------
  // Priority scan for next TX (lowest index = highest priority)
  // --------------------------------------------------------------------------
  always_comb begin
    any_tx_pending = 1'b0;
    next_tx_idx    = '0;
    for (int i = DEPTH-1; i >= 0; i--) begin
      if (mem[i].valid && mem[i].pending_tx && !mem[i].tx_done) begin
        any_tx_pending = 1'b1;
        next_tx_idx    = 6'(i);
      end
    end
  end

  // --------------------------------------------------------------------------
  // Most recently written RX buffer
  // --------------------------------------------------------------------------
  always_comb begin
    any_rx_ready = 1'b0;
    next_rx_idx  = '0;
    for (int i = 0; i < DEPTH; i++) begin
      if (mem[i].valid && mem[i].rx_done) begin
        any_rx_ready = 1'b1;
        next_rx_idx  = 6'(i);
      end
    end
  end

endmodule : canfd_msg_ram

// =============================================================================
// SUB-MODULE 9: canfd_error_handler
// ISO 11898-1 fault confinement.
// Maintains TX Error Counter (TEC) and RX Error Counter (REC).
// Transitions node between Error-Active, Error-Passive, and Bus-Off.
// =============================================================================
import canfd_pkg::*;

module canfd_error_handler (
  input  logic        clk,
  input  logic        rst_n,

  // Error events (pulses from other sub-modules)
  input  error_type_e error_in,
  input  logic        error_valid,
  input  logic        tx_error_valid,
  input  logic        rx_success,    // Pulse: clean RX frame received
  input  logic        tx_success,    // Pulse: clean TX frame transmitted + ACK

  // Bus-off recovery
  input  logic        busoff_recover_req,  // Software writes to request recovery

  // Status outputs
  output logic [7:0]  tec,
  output logic [7:0]  rec,
  output node_state_e node_state,
  output logic        bus_off_irq,   // Pulse when entering bus-off
  output logic        err_passive_irq
);

  logic [8:0] tec_wide; // 9-bit to detect overflow past 255
  logic [8:0] rec_wide;
  logic [9:0] busoff_recovery_cnt; // Count 128 × 11 recessive bits

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      tec_wide            <= '0;
      rec_wide            <= '0;
      node_state          <= NODE_ERROR_ACTIVE;
      bus_off_irq         <= 1'b0;
      err_passive_irq     <= 1'b0;
      busoff_recovery_cnt <= '0;
    end else begin
      bus_off_irq     <= 1'b0;
      err_passive_irq <= 1'b0;

      // ── Error counter increment rules (ISO 11898-1 Table 6) ───────────────
      if (error_valid && node_state != NODE_BUS_OFF) begin
        case (error_in)
          ERR_BIT, ERR_FORM, ERR_STUFF, ERR_CRC: begin
            if (tx_error_valid) tec_wide <= tec_wide + 9'd8;
            else                rec_wide <= rec_wide + 9'd1;
          end
          ERR_ACK: begin
            tec_wide <= tec_wide + 9'd8;
          end
          default: ;
        endcase
      end

      // ── Successful transmission / reception decrements ─────────────────────
      if (tx_success && tec_wide > 0)
        tec_wide <= tec_wide - 9'd1;

      if (rx_success && rec_wide > 0)
        rec_wide <= (rec_wide > 9'd127) ? 9'd119 : rec_wide - 9'd1;

      // ── State transitions ──────────────────────────────────────────────────
      case (node_state)
        NODE_ERROR_ACTIVE: begin
          if (tec_wide >= 9'd128 || rec_wide >= 9'd128) begin
            node_state      <= NODE_ERROR_PASSIVE;
            err_passive_irq <= 1'b1;
          end
          if (tec_wide >= 9'd256) begin
            node_state  <= NODE_BUS_OFF;
            tec_wide    <= '0;
            bus_off_irq <= 1'b1;
          end
        end

        NODE_ERROR_PASSIVE: begin
          if (tec_wide < 9'd128 && rec_wide < 9'd128)
            node_state <= NODE_ERROR_ACTIVE;
          if (tec_wide >= 9'd256) begin
            node_state  <= NODE_BUS_OFF;
            tec_wide    <= '0;
            bus_off_irq <= 1'b1;
          end
        end

        NODE_BUS_OFF: begin
          // Recovery: 128 occurrences of 11 consecutive recessive bits
          if (busoff_recover_req) begin
            busoff_recovery_cnt <= busoff_recovery_cnt + 1;
            if (busoff_recovery_cnt >= 10'd128) begin
              busoff_recovery_cnt <= '0;
              tec_wide            <= '0;
              rec_wide            <= '0;
              node_state          <= NODE_ERROR_ACTIVE;
            end
          end
        end
      endcase
    end
  end

  assign tec = tec_wide[7:0];
  assign rec = rec_wide[7:0];

endmodule : canfd_error_handler

// =============================================================================
// TOP MODULE: canfd_controller
// Instantiates and interconnects all sub-modules.
// =============================================================================
import canfd_pkg::*;

module canfd_controller #(
  parameter int unsigned MSG_BUFS   = canfd_pkg::MSG_BUF_COUNT,
  parameter int unsigned APB_AW     = canfd_pkg::APB_ADDR_W,
  parameter int unsigned APB_DW     = canfd_pkg::APB_DATA_W
)(
  input  logic              clk,
  input  logic              rst_n,

  // APB slave (configuration port)
  input  logic [APB_AW-1:0] paddr,
  input  logic              psel,
  input  logic              penable,
  input  logic              pwrite,
  input  logic [APB_DW-1:0] pwdata,
  output logic [APB_DW-1:0] prdata,
  output logic              pready,
  output logic              pslverr,

  // CAN bus pins
  output logic              can_tx,
  input  logic              can_rx,

  // Interrupt
  output logic              irq
);

  // ==========================================================================
  // Internal wires between sub-modules
  // ==========================================================================

  // -- Regmap outputs --------------------------------------------------------
  bit_timing_t  nom_timing, fd_timing;
  logic         reg_fd_enable, reg_tx_enable, reg_loopback, reg_listenonly;
  logic [5:0]   reg_tx_buf_sel;
  logic         reg_tx_request;
  logic [7:0]   reg_rx_filter_id, reg_rx_filter_mask;

  // -- BTU outputs -----------------------------------------------------------
  logic         tq_pulse, sample_point_sig, tx_point_sig, seg1_active_sig;
  logic [7:0]   tq_count_sig;

  // -- TXRX outputs ----------------------------------------------------------
  logic         rx_bit_raw, rx_bit_raw_valid;
  logic         bit_error_sig;
  bus_state_e   bus_state_sig;

  // -- Stuffing (TX path) outputs --------------------------------------------
  logic         tx_stuff_bit, tx_stuff_valid;

  // -- Stuffing (RX path) outputs -------------------------------------------
  logic         rx_destuff_bit, rx_destuff_valid;
  logic         stuff_error_sig;

  // -- CRC outputs -----------------------------------------------------------
  logic [20:0]  crc_out_sig;
  logic         crc_reset_sig, crc_enable_sig;

  // -- Frame RX outputs ------------------------------------------------------
  canfd_frame_t rx_frame_sig;
  logic         rx_frame_valid_sig;
  logic [5:0]   rx_buf_idx_sig;
  error_type_e  rx_error_sig;
  logic         rx_error_valid_sig;
  logic         send_ack_sig;

  // -- Frame TX outputs ------------------------------------------------------
  logic         tx_serial_bit, tx_serial_valid;
  logic         tx_done_sig, tx_active_sig;
  error_type_e  tx_error_type_sig;
  logic         tx_error_valid_sig;
  logic         tx_frame_ack_sig;

  // -- Message RAM outputs ---------------------------------------------------
  msg_buf_t     ctrl_rd_data_sig;
  logic         any_tx_pending_sig;
  logic [5:0]   next_tx_idx_sig;
  logic         any_rx_ready_sig;
  logic [5:0]   next_rx_idx_sig;

  // -- Error handler outputs -------------------------------------------------
  logic [7:0]   tec_sig, rec_sig;
  node_state_e  node_state_sig;
  logic         bus_off_irq_sig, err_passive_irq_sig;

  // -- Combined error for error handler --------------------------------------
  error_type_e  active_error;
  logic         active_error_valid;
  logic         rx_success_sig, tx_success_sig;

  // -- FD data-phase active (BRS received and in data section) ---------------
  logic         fd_data_phase;

  // ==========================================================================
  // Sub-module instantiations
  // ==========================================================================

  // --------------------------------------------------------------------------
  // 1. Register Map
  // --------------------------------------------------------------------------
  canfd_regmap #(
    .ADDR_W (APB_AW),
    .DATA_W (APB_DW)
  ) u_regmap (
    .pclk              (clk),
    .presetn           (rst_n),
    .paddr             (paddr),
    .psel              (psel),
    .penable           (penable),
    .pwrite            (pwrite),
    .pwdata            (pwdata),
    .prdata            (prdata),
    .pready            (pready),
    .pslverr           (pslverr),
    .reg_nom_timing    (nom_timing),
    .reg_fd_timing     (fd_timing),
    .reg_fd_enable     (reg_fd_enable),
    .reg_tx_enable     (reg_tx_enable),
    .reg_loopback      (reg_loopback),
    .reg_listenonly    (reg_listenonly),
    .reg_tx_buf_sel    (reg_tx_buf_sel),
    .reg_tx_request    (reg_tx_request),
    .reg_rx_filter_id  (reg_rx_filter_id),
    .reg_rx_filter_mask(reg_rx_filter_mask),
    .sta_bus_off       (node_state_sig == NODE_BUS_OFF),
    .sta_error_passive (node_state_sig == NODE_ERROR_PASSIVE),
    .sta_tec           (tec_sig),
    .sta_rec           (rec_sig),
    .sta_rx_ready      (any_rx_ready_sig),
    .sta_rx_buf_idx    (next_rx_idx_sig),
    .sta_tx_done       (tx_done_sig),
    .sta_last_error    (active_error),
    .irq_out           (irq)
  );

  // --------------------------------------------------------------------------
  // 2. Bit Timing Unit
  // --------------------------------------------------------------------------
  canfd_btu u_btu (
    .clk            (clk),
    .rst_n          (rst_n),
    .nom_timing     (nom_timing),
    .fd_timing      (fd_timing),
    .fd_active      (fd_data_phase),
    .hard_sync_req  (!rx_bit_raw && bus_state_sig == BUS_IDLE),
    .tq_pulse       (tq_pulse),
    .sample_point   (sample_point_sig),
    .tx_point       (tx_point_sig),
    .seg1_active    (seg1_active_sig),
    .tq_count       (tq_count_sig)
  );

  // --------------------------------------------------------------------------
  // 3. TX/RX Serialiser
  // --------------------------------------------------------------------------
  canfd_txrx u_txrx (
    .clk            (clk),
    .rst_n          (rst_n),
    .sample_point   (sample_point_sig),
    .tx_point       (tx_point_sig),
    .tx_enable      (reg_tx_enable && !reg_listenonly),
    .loopback       (reg_loopback),
    .tx_bit         (tx_stuff_bit),
    .tx_bit_valid   (tx_stuff_valid),
    .can_tx         (can_tx),
    .can_rx         (can_rx),
    .rx_bit         (rx_bit_raw),
    .rx_bit_valid   (rx_bit_raw_valid),
    .bit_error      (bit_error_sig),
    .bus_state      (bus_state_sig)
  );

  // --------------------------------------------------------------------------
  // 4a. Bit Stuffing — TX path
  // --------------------------------------------------------------------------
  canfd_stuffing u_stuff_tx (
    .clk            (clk),
    .rst_n          (rst_n),
    .tx_mode        (1'b1),
    .fd_frame       (ctrl_rd_data_sig.frame.fd_frame),
    .in_crc_field   (1'b0),        // Simplified; full design tracks field
    .bit_in         (tx_serial_bit),
    .bit_en         (tx_serial_valid && tx_point_sig),
    .bit_out        (tx_stuff_bit),
    .bit_out_valid  (tx_stuff_valid),
    .stuff_error    ()              // Not used on TX path
  );

  // --------------------------------------------------------------------------
  // 4b. Bit De-stuffing — RX path
  // --------------------------------------------------------------------------
  canfd_stuffing u_destuff_rx (
    .clk            (clk),
    .rst_n          (rst_n),
    .tx_mode        (1'b0),
    .fd_frame       (1'b0),        // Updated mid-frame in real design
    .in_crc_field   (1'b0),
    .bit_in         (rx_bit_raw),
    .bit_en         (rx_bit_raw_valid),
    .bit_out        (rx_destuff_bit),
    .bit_out_valid  (rx_destuff_valid),
    .stuff_error    (stuff_error_sig)
  );

  // --------------------------------------------------------------------------
  // 5. CRC Engine
  // --------------------------------------------------------------------------
  canfd_crc u_crc (
    .clk            (clk),
    .rst_n          (rst_n),
    .enable         (crc_enable_sig),
    .data_bit       (rx_destuff_bit),
    .fd_frame       (reg_fd_enable),
    .long_payload   (1'b0),        // Driven by frame_rx in full design
    .crc_reset      (crc_reset_sig),
    .crc_out        (crc_out_sig),
    .crc_valid      ()
  );

  // --------------------------------------------------------------------------
  // 6. Frame Assembler (RX)
  // --------------------------------------------------------------------------
  canfd_frame_rx u_frame_rx (
    .clk              (clk),
    .rst_n            (rst_n),
    .rx_bit           (rx_destuff_bit),
    .rx_bit_valid     (rx_destuff_valid),
    .crc_computed     (crc_out_sig),
    .crc_reset        (crc_reset_sig),
    .crc_enable       (crc_enable_sig),
    .stuff_error      (stuff_error_sig),
    .bit_error        (bit_error_sig),
    .filter_id        (reg_rx_filter_id),
    .filter_mask      (reg_rx_filter_mask),
    .rx_frame         (rx_frame_sig),
    .rx_frame_valid   (rx_frame_valid_sig),
    .rx_buf_idx       (rx_buf_idx_sig),
    .rx_error         (rx_error_sig),
    .rx_error_valid   (rx_error_valid_sig),
    .send_ack         (send_ack_sig)
  );

  // --------------------------------------------------------------------------
  // 7. Frame Builder (TX)
  // --------------------------------------------------------------------------
  canfd_frame_tx u_frame_tx (
    .clk              (clk),
    .rst_n            (rst_n),
    .tx_point         (tx_point_sig),
    .tx_frame         (ctrl_rd_data_sig.frame),
    .tx_frame_valid   (any_tx_pending_sig && reg_tx_enable),
    .tx_frame_ack     (tx_frame_ack_sig),
    .ack_received     (send_ack_sig),
    .tx_bit           (tx_serial_bit),
    .tx_bit_valid     (tx_serial_valid),
    .tx_done          (tx_done_sig),
    .tx_active        (tx_active_sig),
    .tx_error         (tx_error_type_sig),
    .tx_error_valid   (tx_error_valid_sig)
  );

  // --------------------------------------------------------------------------
  // 8. Message RAM
  // --------------------------------------------------------------------------
  canfd_msg_ram #(
    .DEPTH (MSG_BUFS)
  ) u_msg_ram (
    .clk              (clk),
    .rst_n            (rst_n),
    .ctrl_wr_en       (rx_frame_valid_sig),
    .ctrl_wr_idx      (rx_buf_idx_sig),
    .ctrl_wr_data     (rx_frame_sig),
    .ctrl_rd_idx      (any_tx_pending_sig ? next_tx_idx_sig : reg_tx_buf_sel),
    .ctrl_rd_data     (ctrl_rd_data_sig),
    .tx_done_pulse    (tx_done_sig),
    .tx_done_idx      (next_tx_idx_sig),
    .any_tx_pending   (any_tx_pending_sig),
    .next_tx_idx      (next_tx_idx_sig),
    .any_rx_ready     (any_rx_ready_sig),
    .next_rx_idx      (next_rx_idx_sig)
  );

  // --------------------------------------------------------------------------
  // 9. Error Handler
  // --------------------------------------------------------------------------
  assign active_error       = rx_error_valid_sig ? rx_error_sig     :
                              tx_error_valid_sig  ? tx_error_type_sig :
                              bit_error_sig       ? ERR_BIT           : ERR_NONE;

  assign active_error_valid = rx_error_valid_sig | tx_error_valid_sig | bit_error_sig;
  assign rx_success_sig     = rx_frame_valid_sig;
  assign tx_success_sig     = tx_done_sig && !tx_error_valid_sig;

  canfd_error_handler u_error_handler (
    .clk                (clk),
    .rst_n              (rst_n),
    .error_in           (active_error),
    .error_valid        (active_error_valid),
    .tx_error_valid     (tx_error_valid_sig),
    .rx_success         (rx_success_sig),
    .tx_success         (tx_success_sig),
    .busoff_recover_req (reg_tx_request && (node_state_sig == NODE_BUS_OFF)),
    .tec                (tec_sig),
    .rec                (rec_sig),
    .node_state         (node_state_sig),
    .bus_off_irq        (bus_off_irq_sig),
    .err_passive_irq    (err_passive_irq_sig)
  );

  // --------------------------------------------------------------------------
  // FD data-phase tracking
  // Simple: assert fd_data_phase when BRS seen in RX/TX
  // --------------------------------------------------------------------------
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      fd_data_phase <= 1'b0;
    else if (!tx_active_sig && bus_state_sig == BUS_IDLE)
      fd_data_phase <= 1'b0;
    else if (rx_frame_valid_sig && rx_frame_sig.brs)
      fd_data_phase <= 1'b1;
  end

  // --------------------------------------------------------------------------
  // Simulation checks
  // --------------------------------------------------------------------------
  `ifdef SIMULATION
  always_ff @(posedge clk) begin
    if (active_error_valid && active_error != ERR_NONE)
      $warning("[CANFD] Error event: %s  TEC=%0d  REC=%0d  @%0t",
               active_error.name(), tec_sig, rec_sig, $time);
    if (bus_off_irq_sig)
      $error("[CANFD] Node entered BUS-OFF state @%0t", $time);
    if (rx_frame_valid_sig)
      $display("[CANFD] RX frame: ID=0x%07h  DLC=%0d  FD=%0b  BRS=%0b @%0t",
               rx_frame_sig.id, rx_frame_sig.dlc,
               rx_frame_sig.fd_frame, rx_frame_sig.brs, $time);
  end
  `endif

endmodule : canfd_controller

`default_nettype wire
