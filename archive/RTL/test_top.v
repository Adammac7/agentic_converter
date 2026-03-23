// Basic RTL test file for rtl_converter
// Module name must be "top" to match the synth -top top command

module top (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    input  wire        sel,
    output reg  [7:0]  result,
    output reg         carry
);

    wire [8:0] sum;
    assign sum = a + b;

    // Registered output with sync reset
    always @(posedge clk) begin
        if (rst) begin
            result <= 8'd0;
            carry  <= 1'b0;
        end else begin
            if (sel)
                result <= sum[7:0];   // add mode
            else
                result <= a & b;      // AND mode
            carry <= sum[8];
        end
    end

endmodule
