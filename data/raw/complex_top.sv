// =============================================================================
// complex_top.sv
// ADVANCED RTL PARSING TEST CASE
// 
// Challenges for AI:
// 1. Parameterized widths (DATA_WIDTH, ADDR_WIDTH)
// 2. Vectorized Instances (generate block simulation)
// 3. Port slicing ([MSB:LSB])
// 4. Multiple clock domains (clk_sys, clk_mem)
// =============================================================================

// -----------------------------------------------------------------------------
// Module: dma_reg_file
// Checks: Can the AI handle localparams and non-zero based slicing?
// -----------------------------------------------------------------------------
module dma_reg_file #(
    parameter ADDR_W = 12,
    parameter DATA_W = 32
)(
    input  logic              clk,
    input  logic              rst_n,
    input  logic [ADDR_W-1:0] reg_addr,
    input  logic [DATA_W-1:0] reg_wdata,
    input  logic              reg_wr,
    output logic [DATA_W-1:0] reg_rdata,
    // Configuration outputs to other modules
    output logic [1:0]        chan_enable, // Bit 0: Ch0, Bit 1: Ch1
    output logic [31:0]       src_base_addr,
    output logic [31:0]       dst_base_addr
);
    // stub
endmodule

// -----------------------------------------------------------------------------
// Module: dma_channel (Instantiated twice in top)
// Checks: Can the AI distinguish between two instances of the same module?
// -----------------------------------------------------------------------------
module dma_channel (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic [31:0] base_addr,
    output logic        mem_req,
    output logic [31:0] mem_addr,
    input  logic        mem_gnt,
    output logic [7:0]  fifo_data,
    output logic        fifo_wr
);
    // stub
endmodule

// -----------------------------------------------------------------------------
// Module: arbiter_3to1
// Checks: Complex port naming and high fan-in
// -----------------------------------------------------------------------------
module arbiter_3to1 (
    input  logic        clk,
    input  logic        rst_n,
    // Request array from 3 sources
    input  logic [2:0]  req_vec, 
    output logic [2:0]  gnt_vec,
    // Master Memory Interface
    output logic        m_req,
    output logic [31:0] m_addr,
    input  logic [31:0] ch0_addr,
    input  logic [31:0] ch1_addr,
    input  logic [31:0] cpu_addr
);
    // stub
endmodule

// -----------------------------------------------------------------------------
// Top Level: dma_system_top
// -----------------------------------------------------------------------------
module dma_system_top (
    input  logic        clk_sys,
    input  logic        clk_mem,
    input  logic        rst_n,
    
    // CPU Interface
    input  logic [11:0] cpu_addr,
    input  logic [31:0] cpu_wdata,
    input  logic        cpu_wr,
    output logic [31:0] cpu_rdata,
    
    // External Memory Interface
    output logic        ext_mem_req,
    output logic [31:0] ext_mem_addr,
    input  logic        ext_mem_gnt
);

    // --- Internal Signals ---
    logic [1:0]  w_chan_en;
    logic [31:0] w_src_base, w_dst_base;
    
    // Channel Memory Requests
    logic        w_ch0_req, w_ch1_req;
    logic [31:0] w_ch0_addr, w_ch1_addr;
    logic        w_ch0_gnt, w_ch1_gnt;
    
    // FIFO signals
    logic [7:0]  w_ch0_fifo_val, w_ch1_fifo_val;
    logic        w_ch0_fifo_wr, w_ch1_fifo_wr;

    // --- Instantiations ---

    // 1. Register File (The Controller)
    dma_reg_file #(
        .ADDR_W(12),
        .DATA_W(32)
    ) u_regs (
        .clk           (clk_sys),
        .rst_n         (rst_n),
        .reg_addr      (cpu_addr),
        .reg_wdata     (cpu_wdata),
        .reg_wr        (cpu_wr),
        .reg_rdata     (cpu_rdata),
        .chan_enable   (w_chan_en),
        .src_base_addr (w_src_base),
        .dst_base_addr (w_dst_base)
    );

    // 2. DMA Channel 0 (Source Reader)
    dma_channel u_chan_src (
        .clk       (clk_mem),
        .rst_n     (rst_n),
        .en        (w_chan_en[0]), // Slicing bit 0
        .base_addr (w_src_base),
        .mem_req   (w_ch0_req),
        .mem_addr  (w_ch0_addr),
        .mem_gnt   (w_ch0_gnt),
        .fifo_data (w_ch0_fifo_val),
        .fifo_wr   (w_ch0_fifo_wr)
    );

    // 3. DMA Channel 1 (Destination Writer)
    dma_channel u_chan_dst (
        .clk       (clk_mem),
        .rst_n     (rst_n),
        .en        (w_chan_en[1]), // Slicing bit 1
        .base_addr (w_dst_base),
        .mem_req   (w_ch1_req),
        .mem_addr  (w_ch1_addr),
        .mem_gnt   (w_ch1_gnt),
        .fifo_data (w_ch1_fifo_val),
        .fifo_wr   (w_ch1_fifo_wr)
    );

    // 4. Memory Arbiter
    // Checks if the AI can handle the concatenated vector {w_ch1_req, w_ch0_req, 1'b0}
    arbiter_3to1 u_arb (
        .clk      (clk_mem),
        .rst_n    (rst_n),
        .req_vec  ({w_ch1_req, w_ch0_req, 1'b0}), 
        .gnt_vec  ({w_ch1_gnt, w_ch0_gnt, }), // Intentional trailing comma/empty slice
        .m_req    (ext_mem_req),
        .m_addr   (ext_mem_addr),
        .ch0_addr (w_ch0_addr),
        .ch1_addr (w_ch1_addr),
        .cpu_addr (32'h0)
    );

endmodule