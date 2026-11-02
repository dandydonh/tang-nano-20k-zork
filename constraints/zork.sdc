create_clock -name clk_27mhz -period 37.037 [get_ports {clk_27mhz}]
create_clock -name pixel_clk -period 13.468 [get_nets {pixel_clk}]
set_clock_groups -asynchronous -group [get_clocks {clk_27mhz}] -group [get_clocks {pixel_clk}]
