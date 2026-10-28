#include "std_testcase.h"
void case_sink(int * data)
{
    {
        int source[10] = {0};
        memcpy(data, source, 10*sizeof(int));
        printIntLine(data[0]);
    }
}
void case_entry()
{
    int * data;
    data = NULL;
    data = (int *)ALLOCA(10*sizeof(int));
    case_sink(data);
}
