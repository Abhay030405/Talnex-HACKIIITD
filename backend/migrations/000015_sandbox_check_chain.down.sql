DELETE FROM pipeline_stages
 WHERE pipeline IN ('sandbox_check_project', 'sandbox_check')
   AND stage IN ('route_discovery', 'sandbox_plan', 'sandbox_test', 'sandbox_end');
