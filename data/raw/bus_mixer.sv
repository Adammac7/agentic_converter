module bus_processor (
    input  logic [7:0]  data_vld,  // Width 8
    input  logic [0:0]  enable,    // Width 1
    input  logic [31:0] address,   // Width 32
    output logic [63:0] q_out      // Width 64
);
endmodule

module top_bus (
    input  logic [7:0]  ext_data,
    input  logic        ext_en,
    output logic [63:0] ext_q
);
    logic [31:0] w_addr_internal;

    bus_processor u_proc (
        .data_vld(ext_data),
        .enable(ext_en),
        .address(w_addr_internal),
        .q_out(ext_q)
    );
endmodule