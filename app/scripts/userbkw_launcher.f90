program userbkw_launcher
    implicit none

    integer :: argc, i, status
    character(len=32767) :: argv0, arg, bin_dir, app_dir, main_exe, command

    call get_command_argument(0, argv0)
    bin_dir = dirname(trim(argv0))
    if (len_trim(bin_dir) == 0) bin_dir = "."
    app_dir = dirname(trim(bin_dir))
    if (len_trim(app_dir) == 0) app_dir = "."

    main_exe = trim(app_dir) // "\BKW.exe"
    command = quote_arg(trim(main_exe)) // " --userbkw"

    argc = command_argument_count()
    do i = 1, argc
        call get_command_argument(i, arg)
        command = trim(command) // " " // quote_arg(trim(arg))
    end do

    call execute_command_line(trim(command), exitstat=status)
    call exit(status)

contains
    function dirname(path) result(out)
        character(len=*), intent(in) :: path
        character(len=32767) :: out
        integer :: i

        out = ""
        do i = len_trim(path), 1, -1
            if (path(i:i) == "\" .or. path(i:i) == "/") then
                out = path(1:i-1)
                return
            end if
        end do
    end function dirname

    function quote_arg(value) result(out)
        character(len=*), intent(in) :: value
        character(len=32767) :: out
        integer :: i, n

        out = '"'
        n = 1
        do i = 1, len_trim(value)
            if (value(i:i) == '"') then
                if (n + 2 <= len(out)) then
                    out(n+1:n+2) = '""'
                    n = n + 2
                end if
            else
                if (n + 1 <= len(out)) then
                    out(n+1:n+1) = value(i:i)
                    n = n + 1
                end if
            end if
        end do
        if (n + 1 <= len(out)) then
            out(n+1:n+1) = '"'
            n = n + 1
        end if
        out = out(:n)
    end function quote_arg
end program userbkw_launcher
