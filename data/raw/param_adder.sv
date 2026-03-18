// Test: Can the AI resolve DATA_WIDTH-1 to a width of 16?
module param_adder #(
    parameter DATA_WIDTH = 16,
    parameter STAGES = 2
)(
    input  logic [DATA_WIDTH-1:0] a,
    input  logic [DATA_WIDTH-1:0] b,
    input  logic                  clk,
    input  logic                  rst_n,
    output logic [DATA_WIDTH-1:0] sum,
    output logic                  overflow
);
    // Logic stub
endmodule

module top_param (
    input  logic [15:0] sw_a,
    input  logic [15:0] sw_b,
    input  logic        sys_clk,
    output logic [15:0] led_sum
);
    // Internal wire
    logic w_ovf;

    param_adder #( .DATA_WIDTH(16) ) u_adder (
        .a(sw_a),
        .b(sw_b),
        .clk(sys_clk),
        .rst_n(1'b1),
        .sum(led_sum),
        .overflow(w_ovf)
    );
endmodule