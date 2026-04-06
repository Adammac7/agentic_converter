// =============================================================================
// top.sv
// RTL Parsing Demo Design
//
// Hierarchy:
//   top
//   ├── u_ctrl           (ctrl)
//   ├── u_datapath       (datapath)
//   ├── u_memory_intf    (memory_intf)
//   ├── u_fifo           (fifo)
//   └── u_output_formatter (output_formatter)
//
// Connection summary:
//   top         <-> ctrl, datapath, memory_intf, fifo, output_formatter
//   ctrl        <-> datapath (start), memory_intf (mem_req, mem_addr)
//   datapath    <-> memory_intf (mem_data, mem_ack), fifo (wr_en, din, valid)
//   fifo        <-> output_formatter (rd_en, dout, empty)
// =============================================================================

// -----------------------------------------------------------------------------
// Module: ctrl
//   Inputs : clk, rst_n, enable, cfg_mode[1:0]
//   Outputs: start, done, mem_req, mem_addr[7:0]
// -----------------------------------------------------------------------------
module ctrl (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  logic [1:0]  cfg_mode,
    output logic        start,
    output logic        done,
    output logic        mem_req,
    output logic [7:0]  mem_addr
);
    // stub - no implementation
endmodule


// -----------------------------------------------------------------------------
// Module: datapath
//   Inputs : clk, rst_n, start, data_in[7:0], mem_data[7:0], mem_ack
//   Outputs: data_out[7:0], valid, wr_en
// -----------------------------------------------------------------------------
module datapath (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic [7:0]  data_in,
    input  logic [7:0]  mem_data,
    input  logic        mem_ack,
    output logic [7:0]  data_out,
    output logic        valid,
    output logic        wr_en
);
    // stub - no implementation
endmodule


// -----------------------------------------------------------------------------
// Module: memory_intf
//   Inputs : clk, rst_n, mem_req, mem_addr[7:0]
//   Outputs: mem_data[7:0], mem_ack
// -----------------------------------------------------------------------------
module memory_intf (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        mem_req,
    input  logic [7:0]  mem_addr,
    output logic [7:0]  mem_data,
    output logic        mem_ack
);
    // stub - no implementation
endmodule


// -----------------------------------------------------------------------------
// Module: fifo
//   Inputs : clk, rst_n, wr_en, din[7:0], rd_en
//   Outputs: dout[7:0], full, empty
// -----------------------------------------------------------------------------
module fifo (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wr_en,
    input  logic [7:0]  din,
    input  logic        rd_en,
    output logic [7:0]  dout,
    output logic        full,
    output logic        empty
);
    // stub - no implementation
endmodule


// -----------------------------------------------------------------------------
// Module: output_formatter
//   Inputs : clk, rst_n, raw_data[7:0], data_valid, empty
//   Outputs: result[7:0], result_valid, rd_en
// -----------------------------------------------------------------------------
module output_formatter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  raw_data,
    input  logic        data_valid,
    input  logic        empty,
    output logic [7:0]  result,
    output logic        result_valid,
    output logic        rd_en
);
    // stub - no implementation
endmodule


// -----------------------------------------------------------------------------
// Module: top
//   Top-level wrapper.  Instantiates all five sub-modules and wires them
//   together via internal nets.
// -----------------------------------------------------------------------------
module top (
    // Global clocking / reset
    input  logic        clk,
    input  logic        rst_n,
    // External control inputs
    input  logic        enable,
    input  logic [1:0]  cfg_mode,
    // External data input (to datapath)
    input  logic [7:0]  data_in,
    // External outputs
    output logic        done,
    output logic [7:0]  result,
    output logic        result_valid
);

    // -------------------------------------------------------------------------
    // Internal signals
    // -------------------------------------------------------------------------

    // ctrl -> datapath
    logic        w_start;

    // ctrl -> memory_intf
    logic        w_mem_req;
    logic [7:0]  w_mem_addr;

    // memory_intf -> datapath
    logic [7:0]  w_mem_data;
    logic        w_mem_ack;

    // datapath -> fifo
    logic        w_wr_en;
    logic [7:0]  w_dp_data_out;
    logic        w_dp_valid;

    // output_formatter -> fifo
    logic        w_rd_en;

    // fifo -> output_formatter
    logic [7:0]  w_fifo_dout;
    logic        w_fifo_full;
    logic        w_fifo_empty;

    // -------------------------------------------------------------------------
    // Sub-module instantiations
    // -------------------------------------------------------------------------

    ctrl u_ctrl (
        .clk      (clk),
        .rst_n    (rst_n),
        .enable   (enable),
        .cfg_mode (cfg_mode),
        .start    (w_start),
        .done     (done),
        .mem_req  (w_mem_req),
        .mem_addr (w_mem_addr)
    );

    datapath u_datapath (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (w_start),
        .data_in  (data_in),
        .mem_data (w_mem_data),
        .mem_ack  (w_mem_ack),
        .data_out (w_dp_data_out),
        .valid    (w_dp_valid),
        .wr_en    (w_wr_en)
    );

    memory_intf u_memory_intf (
        .clk      (clk),
        .rst_n    (rst_n),
        .mem_req  (w_mem_req),
        .mem_addr (w_mem_addr),
        .mem_data (w_mem_data),
        .mem_ack  (w_mem_ack)
    );

    fifo u_fifo (
        .clk   (clk),
        .rst_n (rst_n),
        .wr_en (w_wr_en),
        .din   (w_dp_data_out),
        .rd_en (w_rd_en),
        .dout  (w_fifo_dout),
        .full  (w_fifo_full),
        .empty (w_fifo_empty)
    );

    output_formatter u_output_formatter (
        .clk          (clk),
        .rst_n        (rst_n),
        .raw_data     (w_fifo_dout),
        .data_valid   (w_dp_valid),
        .empty        (w_fifo_empty),
        .result       (result),
        .result_valid (result_valid),
        .rd_en        (w_rd_en)
    );

endmodule
 