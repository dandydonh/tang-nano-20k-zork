create_clock -name clk_27mhz -period 37.037 [get_ports {clk_27mhz}]
create_clock -name pixel_clk -period 13.468 [get_nets {pixel_clk}]
set_clock_groups -asynchronous -group [get_clocks {clk_27mhz}] -group [get_clocks {pixel_clk}]
# Integrated SDRAM uses the opposite edge of the 27 MHz CPU clock.
create_generated_clock -name sdram_clk -source [get_ports {clk_27mhz}] -divide_by 1 -invert [get_ports {O_sdram_clk}]
set_output_delay -clock [get_clocks {sdram_clk}] -max 3.0 [get_ports {O_sdram_cke O_sdram_cs_n O_sdram_ras_n O_sdram_cas_n O_sdram_wen_n O_sdram_addr[*] O_sdram_ba[*] O_sdram_dqm[*] IO_sdram_dq[*]}]
set_output_delay -clock [get_clocks {sdram_clk}] -min -2.0 [get_ports {O_sdram_cke O_sdram_cs_n O_sdram_ras_n O_sdram_cas_n O_sdram_wen_n O_sdram_addr[*] O_sdram_ba[*] O_sdram_dqm[*] IO_sdram_dq[*]}]
set_input_delay -clock [get_clocks {sdram_clk}] -max 10.0 [get_ports {IO_sdram_dq[*]}]
set_input_delay -clock [get_clocks {sdram_clk}] -min 0.0 [get_ports {IO_sdram_dq[*]}]
