set project_dir [file normalize [file join [file dirname [info script]] ..]]
cd $project_dir
open_project zork.gprj
set_option -top_module zork_top
set_option -output_base_name zork
set_option -gen_text_timing_rpt 1
if {[catch {run all} build_error]} {
  puts stderr $build_error
  exit 1
}
