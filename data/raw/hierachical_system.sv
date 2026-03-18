module leaf_node (
    input  logic d_in,
    output logic d_out
);
    assign d_out = ~d_in;
endmodule

module mid_level (
    input  logic m_in,
    output logic m_out
);
    leaf_node u_leaf (.d_in(m_in), .d_out(m_out));
endmodule

module top_hierarchy (
    input  logic sys_in,
    output logic sys_out
);
    // The agent must catch that top instantiates mid_level, 
    # and mid_level is defined above.
    mid_level u_mid (.m_in(sys_in), .m_out(sys_out));
endmodule